(function () {
  const pages = {
    digest: {
      title: 'AI-агент управления бизнесом',
      subtitle: 'Финансовый дайджест',
      icon: 'bi-chat-square-text',
      href: '/digest',
    },
    price: {
      title: 'Прайс-лист',
      subtitle: 'Цены, остатки и резервы',
      icon: 'bi-tags',
      href: '/price-list',
    },
    managers: {
      title: 'Дашборд менеджеров',
      subtitle: 'KPI и выполнение плана',
      icon: 'bi-people',
      href: '/dashboard/managers',
    },
    sales: {
      title: 'Отчет по продажам',
      subtitle: 'Продажи, контрагенты и номенклатура',
      icon: 'bi-bar-chart',
      href: '/report/sales',
    },
    chat: {
      title: 'ИИ-ассистент',
      subtitle: 'Вопросы по данным 1С',
      icon: 'bi-stars',
      href: '/chat',
    },
    settings: {
      title: 'Настройки клиента',
      subtitle: 'Подключение и параметры 1С',
      icon: 'bi-sliders',
      href: '/account/settings',
    },
    prompts: {
      title: 'Промпты',
      subtitle: 'Настройки AI-инструкций',
      icon: 'bi-chat-square-text',
      href: '/prompts',
    },
  };

  const navOrder = ['digest', 'price', 'managers', 'sales', 'chat', 'settings'];

  function navItem(key, active) {
    const page = pages[key];
    const activeClass = key === active ? ' is-active' : '';
    return `
      <a class="sp-nav-item${activeClass}" href="${page.href}">
        <span class="sp-nav-icon"><i class="bi ${page.icon}"></i></span>
        <span class="sp-nav-text">
          <strong>${page.title === 'AI-агент управления бизнесом' ? 'AI-агент' : page.title}</strong>
          <small>${page.subtitle}</small>
        </span>
      </a>
    `;
  }

  function importantPanel() {
    return `
      <section class="sp-important-card">
        <div class="sp-card-title"><span><i class="bi bi-activity"></i></span>Сегодня важно</div>
        <div class="sp-alert sp-alert-red">
          <span><i class="bi bi-arrow-down-right"></i></span>
          <div><strong>Продажи снизились на 12%</strong><small>По сравнению с прошлой неделей</small></div>
        </div>
        <div class="sp-alert sp-alert-orange">
          <span><i class="bi bi-graph-up-arrow"></i></span>
          <div><strong>Дебиторская задолженность растет</strong><small>+1.8 млн ₽ за последние 7 дней</small></div>
        </div>
        <div class="sp-alert sp-alert-amber">
          <span><i class="bi bi-box-seam"></i></span>
          <div><strong>15 товаров с низкой оборачиваемостью</strong><small>Рекомендуется принять меры</small></div>
        </div>
        <div class="sp-alert sp-alert-red">
          <span><i class="bi bi-person-exclamation"></i></span>
          <div><strong>3 менеджера выбиваются из плана</strong><small>Ниже 80% выполнения</small></div>
        </div>
        <a href="/dashboard/managers" class="sp-view-all">Смотреть все аномалии <i class="bi bi-arrow-right"></i></a>
      </section>
    `;
  }

  document.addEventListener('DOMContentLoaded', function () {
    const body = document.body;
    if (!body || body.dataset.shellReady === 'true' || body.dataset.appShell !== 'true') return;

    const active = body.dataset.active || 'digest';
    const page = pages[active] || pages.digest;
    const content = document.createElement('main');
    content.className = 'sp-content';

    Array.from(body.children).forEach((child) => {
      if (child.tagName === 'SCRIPT') return;
      content.appendChild(child);
    });

    const shell = document.createElement('div');
    shell.className = 'sp-shell';
    shell.innerHTML = `
      <aside class="sp-sidebar">
        <a class="sp-brand" href="/digest">
          <span class="sp-brand-mark"><i class="bi bi-box-fill"></i></span>
          <strong>Сервисы 1С</strong>
        </a>
        <nav class="sp-nav">${navOrder.map((key) => navItem(key, active)).join('')}</nav>
        <a class="sp-collapse" href="/logout"><i class="bi bi-box-arrow-right"></i><span>Выйти</span></a>
      </aside>
      <section class="sp-workspace">
        <header class="sp-topbar">
          <div class="sp-heading">
            <span class="sp-dot"></span>
            <h1>${page.title}</h1>
          </div>
          <a class="sp-user" href="/logout">
            <span><i class="bi bi-person-fill"></i></span>
            <strong>Руководитель</strong>
            <i class="bi bi-chevron-down"></i>
          </a>
        </header>
        <div class="sp-main-grid">
          <div class="sp-main-slot"></div>
          <aside class="sp-right-panel">${importantPanel()}</aside>
        </div>
      </section>
    `;

    shell.querySelector('.sp-main-slot').appendChild(content);
    body.insertBefore(shell, body.firstChild);
    body.dataset.shellReady = 'true';
  });
})();
