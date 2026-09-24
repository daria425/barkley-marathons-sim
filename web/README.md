# Runner scene development

Run `npm run dev -- --mode dev --port 5174` and open the **Runner** slide.
The scene animates automatically using the mock runner and environment. In live mode,
it follows the broadcast state. Hidden slides/browser tabs suspend rendering automatically.
The temporary Preview Studio and manual scene play/pause controls were removed after review.

Scene modules live under `src/components/scene/`. `terrain.ts` owns visual presets;
`conditions.ts` parses the fictional Eastern park clock and resolves weather. The backend's
`current_terrain` and `local_time` arrive through generated API types; don't duplicate them.

Checks: `npm run build`, `npm run lint`, and `node --test tests/scene-conditions.test.mjs`.

---

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
