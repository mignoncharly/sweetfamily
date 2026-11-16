import { chromium, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync,writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
const fixture=JSON.parse(process.env.NOEL_UI_FIXTURE);
const origin=`http://127.0.0.1:${fixture.role==='control'?8201:8202}`;
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({reducedMotion:'reduce'});
await context.addCookies(fixture.cookies);
const page=await context.newPage();
const output=new URL('../../.local/ui-results/',import.meta.url);mkdirSync(output,{recursive:true});
const scans=[];
async function scan(name, target=page) {
 const result=await new AxeBuilder({page:target}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']).analyze();
 scans.push({name,violations:result.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}))});
 expect(scans.at(-1).violations,JSON.stringify(scans.at(-1))).toEqual([]);
}
async function layouts(name) {
 for (const width of [360,390,768,1440]) {
  await page.setViewportSize({width,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:new URL(`${fixture.role}-${name}-${width}.png`,output).pathname.replace(/^\/(.:)/,'$1'),fullPage:true});
 }
 // 1440px at 200% browser zoom has a 720 CSS-pixel layout viewport.
 await page.setViewportSize({width:720,height:450});await scan(name+'-200-percent-reflow');
}
try {
 const anonymous=await browser.newContext();const login=await anonymous.newPage();
 await login.goto(origin+'/accounts/login/code/');await scan('login-code',login);
 await login.locator('[name=email]').fill(fixture.email);
 await login.locator('form button[type=submit]').click();
 await expect(login.locator('[name=code]')).toBeVisible();await scan('login-code-confirm',login);await anonymous.close();
 await page.goto(origin+'/');await scan('home');await layouts('home');
 await page.goto(origin+'/help');await scan('help');
 await page.keyboard.press('Tab');await expect(page.locator('.skip')).toBeFocused();
 await page.keyboard.press('Enter');await expect(page.locator('#content')).toBeFocused();
 if(fixture.role==='control') {
  await page.goto(origin+'/events/new');await scan('create');
  await page.getByLabel(/Nom de l.événement/).fill('Noël d’Éloïse — '+ 'famille '.repeat(9));
  await page.locator('[name=celebration_at]').fill('2026-12-24T18:00');
  await page.locator('[name=wishlist_deadline]').fill('2026-12-01T18:00');
  await page.route('**/events/new',route=>route.request().method()==='POST'?route.abort():route.continue());
  await page.getByRole('button',{name:'Créer le brouillon'}).click();
  await expect(page.locator('[data-form-status]')).toContainText('Enregistrement non confirmé');
  await expect(page.locator('[name=title]')).toHaveValue(/Noël d’Éloïse/);
  await page.unroute('**/events/new');
  // Genuine missing session, then refresh only the CSRF token after reconnecting.
  const cookies=await context.cookies();await context.clearCookies();
  await page.getByRole('button',{name:'Créer le brouillon'}).click();
  await expect(page.locator('[data-form-status]')).toContainText('Session expirée');
  await context.addCookies(cookies);
  await page.getByRole('button',{name:'Reprendre après connexion'}).click();
  await expect(page.getByRole('button',{name:/Session reprise/})).toBeDisabled();
  await page.getByRole('button',{name:'Créer le brouillon'}).click();
  await expect(page.locator('h1')).toContainText('Noël d’Éloïse');
  await scan('dashboard-empty');const dashboard=page.url();
  for(let i=0;i<4;i++) {
   await page.getByRole('link',{name:'Ajouter une personne',exact:true}).click();
   await page.locator('[name=display_name]').fill(['Éloïse','François','Maëlle','Jérôme'][i]);
   await page.locator('[name=country]').selectOption(i%2?'FR':'DE');
   await page.locator('[name=email]').fill(`ui-person-${i}@example.invalid`);
   await page.locator('form button').click();await expect(page).toHaveURL(dashboard);
  }
  await scan('dashboard-four');await layouts('dashboard-four');
  await page.getByRole('link',{name:'Dates et règles',exact:true}).click();await scan('rules-form');
  await page.getByLabel(/Nom de l.événement/).fill('Saisie à conserver');
  const second=await context.newPage();await second.goto(page.url());
  await second.getByLabel(/Nom de l.événement/).fill('Modifié dans une autre fenêtre');
  await second.locator('form button').click();await expect(second).toHaveURL(dashboard);await second.close();
  await page.locator('form button').click();await expect(page.locator('.error-summary')).toBeVisible();
  await expect(page.locator('[name=title]')).toHaveValue('Saisie à conserver');await scan('conflict');
 } else {
  const suffix='?event_id='+fixture.event_id;
  for(const route of ['/profile','/wishlist','/rules','/notifications','/merchant','/withdraw']) {
   await page.goto(origin+route+suffix);await scan(route);await layouts(route.slice(1));
  }
  await page.goto(origin+'/wishlist'+suffix);
  await page.locator('[name=form-0-title]').fill('Ma saisie conservée');
  const second=await context.newPage();await second.goto(origin+'/wishlist'+suffix);
  await second.locator('[name=form-0-title]').fill('Référence actualisée');
  await second.getByRole('button',{name:'Sauvegarder le brouillon',exact:true}).click();
  await expect(second.getByRole('status').filter({hasText:'validés'})).toBeVisible();await second.close();
  await page.getByRole('button',{name:'Sauvegarder le brouillon',exact:true}).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.locator('[name=form-0-title]')).toHaveValue('Ma saisie conservée');await scan('wishlist-conflict');
  await page.goto(origin+'/private'+suffix);await scan('private-neutral');
  await expect(page.locator('[data-private-content]')).toHaveCount(0);
  await page.getByRole('button',{name:'Découvrir mon cadeau à préparer'}).click();
  await expect(page.locator('[data-private-content]')).toBeVisible();await scan('private-revealed');await layouts('private-revealed');
  expect(await page.title()).toBe('Noël Secret — accès personnel');expect(page.url()).not.toContain('Canari');
  await page.locator('[name=note]').fill('Note privée à conserver après une panne');
  await page.route('**/private?*',route=>route.request().method()==='POST'?route.abort():route.continue());
  await page.getByRole('button',{name:'Enregistrer ma préparation',exact:true}).click();
  await expect(page.locator('[data-form-status]')).toContainText('Enregistrement non confirmé');
  await expect(page.locator('[name=note]')).toHaveValue('Note privée à conserver après une panne');await page.unroute('**/private?*');
  await page.keyboard.press('Escape');await expect(page.locator('[data-private-content]')).toHaveCount(0);
  await expect(page.locator('[data-reveal-form] button')).toBeFocused();
  await page.getByRole('button',{name:'Découvrir mon cadeau à préparer'}).click();
  await expect(page.locator('[data-private-content]')).toBeVisible();
  await page.getByRole('button',{name:'Masquer immédiatement (Échap)',exact:true}).click();
  await expect(page.locator('[data-private-content]')).toHaveCount(0);
  await page.getByRole('button',{name:'Découvrir mon cadeau à préparer'}).click();
  await expect(page.locator('[data-private-content]')).toBeVisible();
  // Test-only privileged process changes the synthetic event; no diagnostic HTTP route exists.
  execFileSync(process.env.NOEL_TEST_PYTHON,['-c',
    `import django; django.setup(); from vault_core.models import PrivateEvent; from draw_cases import command; from vault_core.domain import apply_command; e=PrivateEvent.objects.get(pk="${fixture.event_id}"); apply_command(command(e,"cancel",confirm=True))`],{env:process.env});
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect(page.locator('[data-private-content]')).toHaveCount(0);
  await expect(page.locator('[data-private-status]')).toContainText('Événement annulé',{timeout:20000});
  await expect(page.locator('[data-reveal-form]')).toBeHidden();await scan('cancelled-old-tab');
 }
 console.log(`${fixture.role}: native Chromium journey, responsive layouts, keyboard, errors, Axe scans passed (${scans.length} scans)`);
} finally {
 writeFileSync(new URL(`${fixture.role}-axe.json`,output),JSON.stringify(scans,null,2));await browser.close();
}
