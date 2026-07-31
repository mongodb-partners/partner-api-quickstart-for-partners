import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'MongoDB Atlas Partner API',
  tagline: 'Integrate with MongoDB Atlas on behalf of your users using OAuth 2.0',
  favicon: 'img/mongodb-leaf.png',

  future: {
    v4: true,
  },

  // GitHub Pages URL: https://<org>.github.io/<repo>/
  url: 'https://10gen.github.io',
  baseUrl: '/atlas-oauth-demos/',

  organizationName: '10gen',
  projectName: 'atlas-oauth-demos',

  onBrokenLinks: 'throw',
  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },
  themes: ['@docusaurus/theme-mermaid'],

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          path: '../docs',
          sidebarPath: './sidebars.ts',
          routeBasePath: '/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/docusaurus-social-card.jpg',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Atlas Partner API',
      logo: {
        alt: 'MongoDB Atlas',
        src: 'img/mongodb-leaf.png',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'partnerSidebar',
          position: 'left',
          label: 'Docs',
        },
        {
          href: 'https://github.com/10gen/atlas-oauth-demos',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Getting Started',
          items: [
            {label: 'Overview', to: '/'},
            {label: 'Quick Start', to: '/quick-start'},
            {label: 'Getting Your Credentials', to: '/getting-credentials'},
          ],
        },
        {
          title: 'Guides',
          items: [
            {label: 'Partner API Guide', to: '/partner-api-guide/overview'},
            {label: 'Lovable Onboarding', to: '/partner-onboarding/lovable'},
          ],
        },
        {
          title: 'Resources',
          items: [
            {
              label: 'Atlas Admin API Reference',
              href: 'https://www.mongodb.com/docs/atlas/reference/api-resources-spec/',
            },
            {
              label: 'MongoDB Developer Center',
              href: 'https://www.mongodb.com/developer/',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} MongoDB, Inc. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'python', 'ini'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
