// postcss.config.mjs
// This configuration file sets up PostCSS to use Tailwind CSS and Autoprefixer.
import tailwindcss from 'tailwindcss';
import autoprefixer from 'autoprefixer';

export default {
  plugins: [tailwindcss, autoprefixer]
};
