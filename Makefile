.PHONY: help run build-extension build-deb install-extension enable-extension disable-extension uninstall-extension clean

EXTENSION_UUID = power-timer@threeaxe

help:
	@echo "Power Timer - Available targets:"
	@echo "  make run                   - Run the standalone Python application"
	@echo "  make build-extension       - Build the GNOME Shell extension package (ZIP)"
	@echo "  make build-deb             - Build the Debian package for the Python application"
	@echo "  make install-extension     - Install the extension locally for testing"
	@echo "  make install-deb           - Build and install the Debian package"
	@echo "  make enable-extension      - Enable the extension"
	@echo "  make disable-extension     - Disable the extension"
	@echo "  make uninstall-extension   - Uninstall the extension"
	@echo "  make clean                 - Clean build artifacts"

run:
	bash launch.sh

build-extension:
	bash build-extension.sh

build-deb:
	bash build.sh

install-extension: build-extension
	gnome-extensions install --force build/$(EXTENSION_UUID).zip

install-deb: build-deb
	sudo apt install ./build/power-timer_1.0.0_all.deb

enable-extension:
	gnome-extensions enable $(EXTENSION_UUID)

disable-extension:
	gnome-extensions disable $(EXTENSION_UUID)

uninstall-extension:
	gnome-extensions uninstall $(EXTENSION_UUID)

clean:
	rm -rf build/
