/* global logError, TextDecoder */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const APP_NAME = 'Power Timer';
const PANEL_ICON = 'alarm-symbolic';
const QUICK_DURATIONS = [15, 30, 60, 120, 180, 240, 300, 360];

const ACTIONS = [
    {key: 'shutdown', label: 'Éteindre', command: 'poweroff'},
    {key: 'reboot', label: 'Redémarrer', command: 'reboot'},
    {key: 'suspend', label: 'Veille', command: 'suspend'},
    {key: 'hibernate', label: 'Hiberner', command: 'hibernate'},
    {key: 'hybrid', label: 'Veille hybride', command: 'hybrid-sleep'},
];

const TEXT_DECODER = new TextDecoder();

function formatDuration(minutes) {
    if (minutes < 60)
        return `${minutes} min`;

    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;

    if (remainder === 0)
        return hours === 1 ? '1 h' : `${hours} h`;

    return `${hours} h ${remainder} min`;
}

function formatRemaining(seconds) {
    if (seconds < 60)
        return `${seconds} s`;

    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;

    if (minutes < 60)
        return remainder === 0 ? `${minutes} min` : `${minutes} min ${remainder} s`;

    const hours = Math.floor(minutes / 60);
    const leftoverMinutes = minutes % 60;

    if (leftoverMinutes === 0)
        return hours === 1 ? '1 h' : `${hours} h`;

    return `${hours} h ${leftoverMinutes.toString().padStart(2, '0')} min`;
}

function readPowerStates() {
    try {
        const [, contents] = GLib.file_get_contents('/sys/power/state');
        return TEXT_DECODER.decode(contents).trim().split(/\s+/).filter(Boolean);
    } catch (_error) {
        return [];
    }
}

function setMenuOrnament(item, checked) {
    if (typeof item.setOrnament === 'function')
        item.setOrnament(checked ? PopupMenu.Ornament.CHECK : PopupMenu.Ornament.NONE);
}

function setMenuSensitive(item, sensitive) {
    if (typeof item.setSensitive === 'function')
        item.setSensitive(sensitive);
    else
        item.reactive = sensitive;
}

function notify(title, message, isError = false) {
    if (isError && typeof Main.notifyError === 'function')
        Main.notifyError(title, message);
    else
        Main.notify(title, message);
}

function spawnCommand(argv) {
    try {
        Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE);
        return true;
    } catch (error) {
        logError(error, `${APP_NAME}: impossible de lancer ${argv.join(' ')}`);
        return false;
    }
}

class PowerTimerIndicator extends PanelMenu.Button {
    constructor() {
        super(0.0, APP_NAME, false);

        this._systemctlPath = GLib.find_program_in_path('systemctl');
        this._powerStates = readPowerStates();
        this._selectedAction = 'shutdown';
        this._selectedDurationMinutes = 60;
        this._deadlineUsec = 0;
        this._tickSourceId = 0;
        this._actionItems = new Map();
        this._durationItems = new Map();

        this.add_child(new St.Icon({
            icon_name: PANEL_ICON,
            style_class: 'system-status-icon',
        }));

        this._statusLabel = new St.Label({text: ''});
        this._buildMenu();
        this._refreshAvailability();
        this._syncUi();

        this.menu.connect('open-state-changed', (_menu, isOpen) => {
            if (isOpen)
                this._refreshAvailability();
            this._syncUi();
        });
    }

    destroy() {
        this._clearTimer();
        super.destroy();
    }

    _buildMenu() {
        const titleItem = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        titleItem.add_child(new St.Label({text: APP_NAME}));
        this.menu.addMenuItem(titleItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const statusItem = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        statusItem.add_child(this._statusLabel);
        this.menu.addMenuItem(statusItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const actionsMenu = new PopupMenu.PopupSubMenuMenuItem('Action');
        for (const action of ACTIONS) {
            const item = new PopupMenu.PopupMenuItem(action.label);
            item.connect('activate', () => this._selectAction(action.key));
            actionsMenu.menu.addMenuItem(item);
            this._actionItems.set(action.key, item);
        }
        this.menu.addMenuItem(actionsMenu);

        const durationMenu = new PopupMenu.PopupSubMenuMenuItem('Durée');
        for (const minutes of QUICK_DURATIONS) {
            const item = new PopupMenu.PopupMenuItem(formatDuration(minutes));
            item.connect('activate', () => this._selectDuration(minutes));
            durationMenu.menu.addMenuItem(item);
            this._durationItems.set(minutes, item);
        }
        this.menu.addMenuItem(durationMenu);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._startItem = new PopupMenu.PopupMenuItem('Démarrer le minuteur');
        this._startItem.connect('activate', () => this._startTimer());
        this.menu.addMenuItem(this._startItem);

        this._cancelItem = new PopupMenu.PopupMenuItem('Annuler le minuteur');
        this._cancelItem.connect('activate', () => this._clearTimer(true));
        this.menu.addMenuItem(this._cancelItem);
    }

    _refreshAvailability() {
        const hasSystemctl = this._systemctlPath !== null;
        const supportsSuspend = this._powerStates.includes('mem');
        const supportsHibernate = this._powerStates.includes('disk');
        const supportsHybrid = supportsSuspend && supportsHibernate;

        this._supportedActions = {
            shutdown: hasSystemctl,
            reboot: hasSystemctl,
            suspend: hasSystemctl && supportsSuspend,
            hibernate: hasSystemctl && supportsHibernate,
            hybrid: hasSystemctl && supportsHybrid,
        };

        for (const action of ACTIONS) {
            const item = this._actionItems.get(action.key);
            if (item !== undefined)
                setMenuSensitive(item, this._supportedActions[action.key]);
        }

        if (!this._supportedActions[this._selectedAction]) {
            const fallbackAction = ACTIONS.find(action => this._supportedActions[action.key]);
            if (fallbackAction !== undefined)
                this._selectedAction = fallbackAction.key;
        }

        setMenuSensitive(this._startItem, hasSystemctl);
        setMenuSensitive(this._cancelItem, this._tickSourceId !== 0);
    }

    _selectAction(actionKey) {
        if (!this._supportedActions[actionKey])
            return;

        this._selectedAction = actionKey;
        this._syncUi();
    }

    _selectDuration(minutes) {
        this._selectedDurationMinutes = minutes;
        this._syncUi();
    }

    _syncUi() {
        for (const action of ACTIONS) {
            const item = this._actionItems.get(action.key);
            if (item !== undefined)
                setMenuOrnament(item, action.key === this._selectedAction);
        }

        for (const minutes of QUICK_DURATIONS) {
            const item = this._durationItems.get(minutes);
            if (item !== undefined)
                setMenuOrnament(item, minutes === this._selectedDurationMinutes);
        }

        const actionLabel = ACTIONS.find(action => action.key === this._selectedAction)?.label ?? 'Action';

        if (this._tickSourceId !== 0) {
            const remainingSeconds = Math.max(0, Math.ceil((this._deadlineUsec - GLib.get_monotonic_time()) / GLib.USEC_PER_SEC));
            this._statusLabel.text = `${actionLabel} dans ${formatRemaining(remainingSeconds)}`;
        } else {
            this._statusLabel.text = `${actionLabel} après ${formatDuration(this._selectedDurationMinutes)}`;
        }

        setMenuSensitive(this._startItem, this._supportedActions[this._selectedAction] && this._systemctlPath !== null);
        setMenuSensitive(this._cancelItem, this._tickSourceId !== 0);
    }

    _startTimer() {
        if (!this._supportedActions[this._selectedAction]) {
            notify(APP_NAME, 'Action non prise en charge.', true);
            return;
        }

        this._clearTimer(false);

        this._deadlineUsec = GLib.get_monotonic_time() + (this._selectedDurationMinutes * GLib.USEC_PER_SEC * 60);
        this._tickSourceId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            const remainingSeconds = Math.max(0, Math.ceil((this._deadlineUsec - GLib.get_monotonic_time()) / GLib.USEC_PER_SEC));

            if (remainingSeconds <= 0) {
                this._tickSourceId = 0;
                this._executeAction();
                this._refreshAvailability();
                this._syncUi();
                return GLib.SOURCE_REMOVE;
            }

            this._syncUi();
            return GLib.SOURCE_CONTINUE;
        });

        this._refreshAvailability();
        this._syncUi();
        notify(APP_NAME, `${ACTIONS.find(action => action.key === this._selectedAction)?.label ?? 'Action'} planifiée dans ${formatDuration(this._selectedDurationMinutes)}.`);
    }

    _clearTimer(showNotification = false) {
        if (this._tickSourceId !== 0) {
            GLib.source_remove(this._tickSourceId);
            this._tickSourceId = 0;
        }

        this._deadlineUsec = 0;

        if (showNotification)
            notify(APP_NAME, 'Minuteur annule.');

        this._refreshAvailability();
        this._syncUi();
    }

    _executeAction() {
        if (this._systemctlPath === null)
            return;

        const action = ACTIONS.find(item => item.key === this._selectedAction);
        if (action === undefined)
            return;

        const argv = [this._systemctlPath, '--check-inhibitors=no', action.command];
        if (!spawnCommand(argv))
            notify(APP_NAME, `Échec de l'exécution de ${action.label}.`, true);
    }
}

export default class PowerTimerExtension extends Extension {
    enable() {
        this._indicator = new PowerTimerIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}