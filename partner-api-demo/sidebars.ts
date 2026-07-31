import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  partnerSidebar: [
    'intro',
    'getting-credentials',
    'quick-start',
    {
      type: 'category',
      label: 'Partner API Guide',
      collapsible: true,
      collapsed: false,
      items: [
        'partner-api-guide/overview',
        'partner-api-guide/enable-delegated-access',
        'partner-api-guide/api-reference',
        'partner-api-guide/fastapi-server',
        'partner-api-guide/troubleshooting',
      ],
    },
    {
      type: 'category',
      label: 'Partner Onboarding',
      collapsible: true,
      collapsed: false,
      items: [
        'partner-onboarding/lovable',
      ],
    },
  ],
};

export default sidebars;
