module.exports = {
  env: { es6: true },
  parserOptions: { ecmaVersion: 2020, sourceType: 'module' },
  rules: {
    'no-undef': 'error',
    'no-unused-vars': ['warn', { args: 'none' }]
  }
};
