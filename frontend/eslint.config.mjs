import next from "eslint-config-next";

// eslint-config-next 16 ships a native flat config array
// (core rules + TypeScript rules + framework ignores) — no FlatCompat needed.
const eslintConfig = [...next];

export default eslintConfig;
