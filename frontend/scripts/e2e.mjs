/**
 * End-to-end browser test (puppeteer-core + your installed Chrome).
 *
 * Prereqs:
 *   - backend  running on http://localhost:8000  (seeded: python -m app.seed)
 *   - frontend running on http://localhost:5173  (npm run dev)
 *
 * Run:  npm run e2e
 * Env:  CHROME_PATH, FRONTEND_URL, API_URL to override defaults.
 */
import puppeteer from 'puppeteer-core'

const CHROME = process.env.CHROME_PATH ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const FRONTEND = process.env.FRONTEND_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:8000'

let passed = 0
const failed = []
const consoleErrors = []

function check(name, cond, detail = '') {
  console.log(`[${cond ? 'PASS' : 'FAIL'}] ${name}${!cond && detail ? ` — ${detail}` : ''}`)
  cond ? passed++ : failed.push(name)
}

async function apiLogin(email) {
  const res = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password: 'password123' }),
  })
  if (!res.ok) throw new Error(`API login failed: ${res.status}`)
  return res.json()
}

async function apiGet(path, token) {
  const res = await fetch(`${API}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

async function textOn(page, selector) {
  return page.$eval(selector, (el) => el.textContent.trim()).catch(() => null)
}

async function hasText(page, text) {
  // innerText respects CSS text-transform, so compare case-insensitively.
  return page.waitForFunction(
    (t) => document.body && document.body.innerText.toLowerCase().includes(t),
    { timeout: 8000 }, text.toLowerCase(),
  ).then(() => true).catch(() => false)
}

function watchPage(page, label) {
  page.on('pageerror', (e) => consoleErrors.push(`[${label}] pageerror: ${e.message}`))
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(`[${label}] console: ${msg.text()}`)
  })
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--window-size=1400,900'],
    defaultViewport: { width: 1400, height: 900 },
  })

  try {
    // ---------- 1. Public login page ----------
    const page = await browser.newPage()
    watchPage(page, 'login')
    await page.goto(`${FRONTEND}/login`, { waitUntil: 'networkidle2' })
    check('login page renders', await hasText(page, 'Sign in to manage batches'))
    check('demo accounts listed', await hasText(page, 'admin@demo.com'))

    // ---------- 2. Sign in through the UI form ----------
    await page.click('button[type="submit"]')
    check('UI login lands on dashboard', await hasText(page, 'Welcome back'))
    check('dashboard shows batch stats', await hasText(page, 'Total batches'))
    check('dashboard shows ML model card', await hasText(page, 'ML risk model'))
    check('dashboard shows anti-counterfeit stat', await hasText(page, 'Flagged for counterfeiting'))
    check('dashboard shows cold-chain stat', await hasText(page, 'Cold-chain breaches'))
    check('model card shows feature importance', await hasText(page, 'Feature importance'))
    check('dashboard: scan trend chart', await hasText(page, 'QR scans'))
    check('dashboard: status donut', await hasText(page, 'Batch status'))
    check('dashboard: risk profile chart', await hasText(page, 'Risk profile'))
    check('nav shows Alerts with badge', await hasText(page, 'Alerts'))

    // ---------- app chrome (logo, nav sections, footer) ----------
    check('sidebar logo rendered',
      Boolean(await page.$('svg[aria-label="TraceCert logo"]')))
    check('mobile menu button present',
      Boolean(await page.$('button[aria-label="Open navigation"]')))
    check('nav grouped into sections', await hasText(page, 'Workspace'))
    check('footer shows version', await hasText(page, 'TraceCert v1.0.0'))
    check('footer shows live API status', await hasText(page, 'API online'))
    check('footer links to API docs', Boolean(await page.$('a[href$="/docs"]')))

    // batch data available for later steps (public verify uses the same list)
    const session = await apiLogin('producer@demo.com')
    const batches0 = await apiGet('/batches', session.access_token)

    // ---------- 3. Batches list + detail ----------
    await page.goto(`${FRONTEND}/batches`, { waitUntil: 'networkidle2' })
    check('batches table renders', await hasText(page, 'Batch code'))
    const searchBox = await page.$('input[placeholder*="Search by batch"]')
    check('batches: search box present', Boolean(searchBox))
    check('batches: CSV export button', await hasText(page, 'Export CSV'))
    check('batches: pagination footer', await hasText(page, 'Showing'))

    const allRows = await page.$$eval('tbody tr', (trs) => trs.length)
    // Drive the React-controlled input the way test libs do (headless clicks
    // don't reliably focus this field, so a native setter + input event it is).
    await page.evaluate(() => {
      const el = document.querySelector('input[placeholder*="Search by batch"]')
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
      setter.call(el, '500ml')
      el.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await new Promise((r) => setTimeout(r, 300))
    const filteredRows = await page.$$eval('tbody tr', (trs) => trs.length)
    check('batches: search filters the table',
      filteredRows === 1 && filteredRows < allRows,
      `all=${allRows} filtered=${filteredRows}`)

    const batchHref = await page.evaluate(() => {
      const a = document.querySelector('a[href^="/batches/"]')
      return a ? a.getAttribute('href') : null
    })
    check('batch rows link to detail', Boolean(batchHref), 'no /batches/:id link found')

    if (batchHref) {
      await page.goto(`${FRONTEND}${batchHref}`, { waitUntil: 'networkidle2' })
      check('batch detail: QC panel', await hasText(page, 'Quality control'))
      check('batch detail: supply chain panel', await hasText(page, 'Supply chain journey'))
      check('batch detail: cold chain panel', await hasText(page, 'Cold chain'))
      check('batch detail: anti-counterfeit panel', await hasText(page, 'Anti-counterfeit'))
      check('batch detail: QR code rendered',
        Boolean(await page.$('img[alt="QR code"]')))
      check('batch detail: cold chain chart drawn',
        Boolean(await page.$('svg path')))
      check('batch detail: traceability strip', await hasText(page, 'Raw material'))
      check('batch detail: supplier lineage shown', await hasText(page, 'Musanze Orchards'))
      check('batch detail: QR download link', await hasText(page, 'Download PNG'))
      check('batch detail: print sheet link', await hasText(page, 'Print label sheet'))
      check('batch detail: full timeline panel', await hasText(page, 'Full timeline'))
      const entryCount = await page.$$eval('[data-testid="batch-timeline"] li',
        (lis) => lis.length)
      check('batch detail: timeline renders entries', entryCount >= 2,
        `entries=${entryCount}`)
      // production is the oldest entry — expand the collapsed list to see it
      await page.evaluate(() => {
        const btn = [...document.querySelectorAll('button')]
          .find((b) => b.textContent.includes('Show all'))
        btn && btn.click()
      })
      check('batch detail: timeline expands to full history',
        await hasText(page, 'Batch produced'))

      // printable QR label sheet (own route, outside the app chrome)
      const printId = batchHref.split('/').pop()
      await page.goto(`${FRONTEND}/print/qr/${printId}`, { waitUntil: 'networkidle2' })
      check('print sheet: header renders', await hasText(page, 'QR label sheet'))
      check('print sheet: print button', await hasText(page, 'Print sheet'))
      const labelImgs = await page.$$eval('img[alt="QR code"]', (imgs) => imgs.length)
      check('print sheet: labels rendered', labelImgs >= 8, `labels=${labelImgs}`)
      check('print sheet: verify path on labels', await hasText(page, '/verify/'))
    }

    // lifecycle hints on a QC-failed batch
    const failedBatch = batches0.find((b) => b.status === 'failed_qc')
    if (failedBatch) {
      await page.goto(`${FRONTEND}/batches/${failedBatch.id}`, { waitUntil: 'networkidle2' })
      check('batch detail: lifecycle hint on failed batch',
        await hasText(page, 'QC failed'))
    }

    // ---------- alerts feed ----------
    await page.goto(`${FRONTEND}/alerts`, { waitUntil: 'networkidle2' })
    check('alerts page renders', await hasText(page, 'Everything needing attention'))
    check('alerts: cloned-QR flag listed', await hasText(page, 'Possible cloned QR code'))
    check('alerts: QC-failure flag listed', await hasText(page, 'Failed quality control'))
    check('alerts: severity filter controls', await hasText(page, 'critical'))

    // ---------- 4. Suppliers page ----------
    await page.goto(`${FRONTEND}/suppliers`, { waitUntil: 'networkidle2' })
    check('suppliers page renders', await hasText(page, 'Suppliers & raw materials'))
    check('supplier list populated', await hasText(page, 'Musanze Orchards'))
    check('supplier performance scorecard shown', await hasText(page, 'lots'))
    check('supplier QC pass rate shown', await hasText(page, 'QC pass'))

    // ---------- 5. Recalls page ----------
    await page.goto(`${FRONTEND}/recalls`, { waitUntil: 'networkidle2' })
    check('recalls page renders', await hasText(page, 'Recalls'))
    check('seeded recall visible', await hasText(page, 'Affected locations'))

    // ---------- 6. Public verification of a genuine code ----------
    const genuine = batches0.find((b) => b.status === 'delivered')
    const suspicious = batches0.find((b) => b.product_name.includes('500ml'))

    const publicPage = await browser.newPage()
    watchPage(publicPage, 'verify')
    await publicPage.goto(`${FRONTEND}/verify/${genuine.batch_code}`, { waitUntil: 'networkidle2' })
    check('verify: genuine product confirmed', await hasText(publicPage, 'Verified genuine product'))
    check('verify: product name shown', await hasText(publicPage, genuine.product_name))
    check('verify: journey timeline shown', await hasText(publicPage, 'Journey'))
    check('verify: verification counter shown', await hasText(publicPage, 'Verification #'))

    // ---------- 7. Public verification of the cloned/suspicious code ----------
    await publicPage.goto(`${FRONTEND}/verify/${suspicious.batch_code}`, { waitUntil: 'networkidle2' })
    check('verify: counterfeit alert raised',
      await hasText(publicPage, 'scanned unusually often'),
      'no anti-counterfeit alert visible')

    // ---------- 8. Unknown code ----------
    await publicPage.goto(`${FRONTEND}/verify/BQ-0000-00000`, { waitUntil: 'networkidle2' })
    check('verify: unknown code rejected',
      await hasText(publicPage, 'No record found for this code'))

    // ---------- 9. Register flow ----------
    const regPage = await browser.newPage()
    watchPage(regPage, 'register')
    await regPage.goto(`${FRONTEND}/login`, { waitUntil: 'networkidle2' })
    await regPage.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Create an account'))
      btn && btn.click()
    })
    check('register form opens', await hasText(regPage, 'Create your traceability account'))
    check('register has role picker', await hasText(regPage, 'Distributor'))

    // ---------- console errors ----------
    check('no browser console/page errors', consoleErrors.length === 0,
      consoleErrors.slice(0, 5).join(' | '))
  } finally {
    await browser.close()
  }

  console.log(`\n${passed}/${passed + failed.length} browser checks passed`)
  if (failed.length) {
    console.log('Failed: ' + failed.join('; '))
    process.exit(1)
  }
}

main().catch((e) => {
  console.error('E2E run crashed:', e)
  process.exit(1)
})
