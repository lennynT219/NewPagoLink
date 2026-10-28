const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');

const landing = readFileSync('landing/templates/landing/layouts/base.html', 'utf8');
const dashboard = readFileSync('dashboard/templates/dashboard/layouts/base.html', 'utf8');
const sidebar = readFileSync('dashboard/templates/dashboard/sidebar.html', 'utf8');

// Only the DOM operations used by these inline handlers; no rendering simulation.
function target() {
    const listeners = new Map();
    return {
        addEventListener(type, callback) {
            if (!listeners.has(type)) listeners.set(type, []);
            listeners.get(type).push(callback);
        },
        fire(type, event = {}) {
            for (const callback of listeners.get(type) || []) callback(event);
        },
    };
}

function mount(source, toggleId, menuId, mobile = true) {
    const document = { ...target(), activeElement: null };
    function element() {
        const classes = new Set();
        const attributes = new Map();
        return {
            ...target(), parent: null,
            classList: {
                add: name => classes.add(name),
                remove: name => classes.delete(name),
                contains: name => classes.has(name),
                toggle(name, force = !classes.has(name)) {
                    if (force) classes.add(name); else classes.delete(name);
                    return force;
                },
            },
            setAttribute: (name, value) => attributes.set(name, String(value)),
            getAttribute: name => attributes.get(name),
            contains(node) {
                return node === this || Boolean(node && this.contains(node.parent));
            },
            closest(selector) { return selector === 'a' && this.isLink ? this : null; },
            focus() { document.activeElement = this; },
        };
    }
    const ids = Object.fromEntries([toggleId, menuId, 'landingNavbar', 'userDropdown'].map(id => [id, element()]));
    const toggle = ids[toggleId];
    const menu = ids[menuId];
    // Seed attributes from real markup, not from the desired implementation.
    const markup = source.match(new RegExp(`<button[^>]*id="${toggleId}"[^>]*>`, 's'))?.[0]
        || source.match(/<button class="sidebar-toggle-btn"[^>]*>/s)?.[0] || '';
    for (const [, name, value] of markup.matchAll(/(aria-[\w-]+)="([^"]*)"/g)) toggle.setAttribute(name, value);
    document.getElementById = id => ids[id];
    const media = { ...target(), matches: mobile };
    const window = { ...target(), scrollY: 0, matchMedia: () => media };
    const context = vm.createContext({ document, window });
    for (const [, script] of source.matchAll(/<script>([\s\S]*?)<\/script>/g)) vm.runInContext(script, context);
    // Preserve support for the original dashboard's inline onclick during RED.
    const onclick = markup.match(/onclick="([^"]*)"/)?.[1];
    if (onclick) toggle.addEventListener('click', () => vm.runInContext(onclick, context));
    function clickAccount(event) {
        const handler = source.match(/<button class="dashboard-navbar-user-btn[^"]*"[^>]*onclick="([^"]*)"/s)[1];
        vm.runInContext(`(function(event) { ${handler} })`, context)(event);
    }
    return { document, window, media, toggle, menu, ids, element, clickAccount };
}

for (const [name, source, toggleId, menuId, breakpoint] of [
    ['landing', landing, 'navToggle', 'navLinks', 992],
    ['dashboard', dashboard, 'sidebarToggle', 'dashboardSidebar', 768],
]) {
    const setup = mobile => mount(source, toggleId, menuId, mobile);
    function state(ui, open) {
        assert.equal(ui.menu.classList.contains('open'), open);
        assert.equal(ui.toggle.getAttribute('aria-expanded'), String(open));
        assert.equal(ui.toggle.getAttribute('aria-controls'), menuId);
    }
    test(`${name}: toggle synchronizes ARIA and existing open state`, () => {
        const ui = setup();
        state(ui, false);
        ui.toggle.fire('click');
        state(ui, true);
        ui.toggle.fire('click');
        state(ui, false);
    });
    test(`${name}: Escape closes and returns focus only for an open mobile menu`, () => {
        const ui = setup();
        ui.toggle.fire('click');
        const link = ui.element();
        link.parent = ui.menu;
        link.focus();
        ui.document.fire('keydown', { key: 'Tab' });
        assert.equal(ui.menu.classList.contains('open'), true);
        ui.document.fire('keydown', { key: 'Escape' });
        state(ui, false);
        assert.equal(ui.document.activeElement, ui.toggle);
        const outside = ui.element();
        outside.focus();
        ui.document.fire('keydown', { key: 'Escape' });
        assert.equal(ui.document.activeElement, outside);
    });
    test(`${name}: outside clicks close without stealing the clicked control's focus`, () => {
        const ui = setup();
        ui.toggle.fire('click');
        ui.document.fire('click', { target: ui.toggle });
        assert.equal(ui.menu.classList.contains('open'), true);
        const inside = ui.element();
        inside.parent = ui.menu;
        ui.document.fire('click', { target: inside });
        assert.equal(ui.menu.classList.contains('open'), true);
        const outside = ui.element();
        outside.focus();
        ui.document.fire('click', { target: outside });
        state(ui, false);
        assert.equal(ui.document.activeElement, outside);
    });
    test(`${name}: selecting a mobile link closes without preventing navigation`, () => {
        const ui = setup();
        const link = ui.element();
        link.parent = ui.menu;
        link.isLink = true;
        link.focus();
        ui.toggle.fire('click');
        ui.menu.fire('click', { target: link, preventDefault() { assert.fail('navigation cancelled'); } });
        state(ui, false);
        assert.equal(ui.document.activeElement, link);
    });
    test(`${name}: preserve desktop navigation and focus on ordinary clicks`, () => {
        const ui = setup(false);
        const link = ui.element();
        link.parent = ui.menu;
        link.isLink = true;
        link.focus();
        ui.menu.fire('click', { target: link, preventDefault() { assert.fail('navigation cancelled'); } });
        ui.document.fire('click', { target: link });
        ui.document.fire('keydown', { key: 'Escape' });
        assert.equal(ui.document.activeElement, link);
        assert.equal(ui.menu.classList.contains('open'), false);
    });
    test(`${name}: desktop resets stale mobile state and never focuses the hidden toggle`, () => {
        const ui = setup();
        ui.toggle.fire('click');
        const link = ui.element();
        link.parent = ui.menu;
        link.focus();
        ui.media.matches = false;
        ui.media.fire('change');
        state(ui, false);
        assert.equal(ui.document.activeElement, link);
        ui.toggle.fire('click');
        ui.document.fire('keydown', { key: 'Escape' });
        state(ui, false);
        assert.equal(ui.document.activeElement, link);
        ui.media.matches = true;
        ui.media.fire('change');
        state(ui, false);
        assert.equal(ui.document.activeElement, ui.toggle);
        assert.ok(source.includes(`(max-width: ${breakpoint}px)`));
    });
}

test('current links use their actual namespaced route, preserving every URL', () => {
    for (const source of [landing.match(/<ul class="nav-links"[\s\S]*?<\/ul>/)[0], sidebar]) {
        for (const [, route, attributes] of source.matchAll(/<a href="\{% url '([^']+)' %\}"([^>]*)>/g)) {
            const condition = `request.resolver_match.view_name == '${route}'`;
            assert.ok(attributes.includes(condition), `${route}: namespaced current condition`);
            assert.ok(attributes.includes(`aria-current="{% if ${condition} %}page{% else %}false{% endif %}"`), route);
            if (source === sidebar) assert.ok(attributes.includes(`{% if ${condition} %} active{% endif %}`), route);
        }
    }
});

test('account control has explicit keyboard focus styling', () => {
    assert.match(dashboard, /\.dashboard-navbar-user-btn:focus-visible\s*\{[^}]*outline:\s*2px solid[^}]*outline-offset:/);
    assert.doesNotMatch(dashboard, /\.dashboard-navbar-user-btn:focus\s*\{[^}]*outline:\s*none/);
});

test('closed mobile sidebar is hidden from keyboard navigation', () => {
    const mobile = dashboard.slice(dashboard.indexOf('@media (max-width: 768px)'));
    assert.match(mobile, /\.dashboard-sidebar\s*\{[^}]*visibility:\s*hidden/);
    assert.match(mobile, /\.dashboard-sidebar\.open\s*\{[^}]*visibility:\s*visible/);
});

test('preserve landing scroll threshold and dashboard dropdown outside-click behavior', () => {
    const ui = mount(landing, 'navToggle', 'navLinks');
    for (const [scrollY, scrolled] of [[21, true], [20, false], [0, false]]) {
        ui.window.scrollY = scrollY;
        ui.window.fire('scroll');
        assert.equal(ui.ids.landingNavbar.classList.contains('scrolled'), scrolled);
    }
    const dash = mount(dashboard, 'sidebarToggle', 'dashboardSidebar');
    const dropdown = dash.ids.userDropdown;
    let stopped = 0;
    const event = { stopPropagation() { stopped++; } };
    dash.clickAccount(event);
    assert.equal(stopped, 1);
    assert.equal(dropdown.classList.contains('active'), true);
    dash.clickAccount(event);
    assert.equal(stopped, 2);
    assert.equal(dropdown.classList.contains('active'), false);
    dash.clickAccount(event);
    dash.document.fire('click', { target: dropdown });
    assert.equal(dropdown.classList.contains('active'), true);
    dash.document.fire('click', { target: dash.element() });
    assert.equal(dropdown.classList.contains('active'), false);
    assert.equal(stopped, 3);
});
