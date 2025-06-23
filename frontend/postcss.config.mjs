// frontend/postcss.config.mjs
export default {
  plugins: {
    "@tailwindcss/postcss": {
      config: "./tailwind.config.ts",
    },
    autoprefixer: {},
  },
}
