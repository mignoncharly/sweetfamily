import { chromium, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';

const fixture = JSON.parse(process.env.NOEL_UI_FIXTURE);
const browser = await chromium.launch({headless:true});
const context = await browser.newContext({viewport:{width:390,height:844}});
const page = await context.newPage();
const scans = [];
const output = new URL('../../.local/ui-results/',import.meta.url);
mkdirSync(output,{recursive:true});
async function scan(name) {
 const result = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']).analyze();
 scans.push({name,violations:result.violations.map(v=>({id:v.id,impact:v.impact}))});
 expect(scans.at(-1).violations).toEqual([]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
}
try {
 const url = fixture.origin+'/accounts/enroll/'+fixture.member_id+'/';
 await page.goto(url); await scan('private-invitation');
 // A GET/preview must leave the same enrollment possible.
 expect((await context.request.get(url)).status()).toBe(200);
 await page.getByLabel(/C.est bien moi/).check();
 await page.getByRole('button',{name:'Demander mon accès'}).click();
 await expect(page).toHaveURL(fixture.origin+'/accounts/enrollment/');
 await scan('waiting-independent-check');
 expect((await context.request.get(fixture.origin+'/api/me/events')).status()).toBe(401);
 const values = await page.locator('dl dd').allTextContents();
 const approvalPath = fixture.directory+'/approval.json';
 // This child represents the independent verifier, outside the web process.
 execFileSync(process.env.NOEL_TEST_PYTHON,['scripts/enrollment_verifier.py','sign',
  '--key-file',fixture.key_file,'--claim-id',values[0].trim(),'--comparison',values[1].trim(),
  '--vault-origin',fixture.vault_origin,'--identity-verified','--output',approvalPath],{stdio:'pipe'});
 execFileSync(process.env.NOEL_TEST_PYTHON,['services/vault/manage.py','approve_enrollment',
  '--approval-file',approvalPath],{stdio:'pipe'});
 await page.reload(); await scan('approved-first-access');
 await page.getByLabel(/Garder ma connexion/).check();
 await page.getByRole('button',{name:'Activer mon accès et obtenir mon code'}).click();
 await scan('personal-code-once');
 const code = (await page.locator('main code').textContent()).trim();
 expect(code.replaceAll('-','').length).toBe(32);
 await page.getByRole('link',{name:/J.ai conservé mon code/}).click();
 await scan('email-free-home');
 await page.getByRole('link',{name:'Mes trois souhaits',exact:true}).click();
 await scan('email-free-wishlist');
 const remembered = (await context.cookies()).find(c=>c.name==='noel_vault_session');
 expect(remembered.expires).toBeGreaterThan(Date.now()/1000+29*86400);
 const second = await browser.newContext();
 const resumed = await second.newPage();
 await resumed.goto(fixture.origin+'/accounts/personal-code/');
 await resumed.locator('input[name=code]').fill(code);
 await resumed.getByRole('button',{name:'Ouvrir mon espace personnel'}).click();
 await expect(resumed.locator('h1')).toHaveText('Mon espace personnel');
 await page.goto(fixture.origin+'/accounts/personal-access/');
 await scan('replace-personal-code');
 await page.locator('input[name=code]').fill(code);
 await page.getByRole('button',{name:/Remplacer mon code et déconnecter/}).click();
 expect((await second.request.get(fixture.origin+'/api/me/events')).status()).toBe(401);
 expect((await context.request.get(url)).status()).toBe(404);
 await second.close();
 writeFileSync(new URL('access-codes-axe.json',output),JSON.stringify({scans},null,2));
 console.log('Email-free browser journey passed; '+scans.length+' Axe scans, no violations.');
} finally { await browser.close(); }
