const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const path = require("node:path");
const [, , url, evidence] = process.argv;
const target = "#Advanced/Device/SysLog?type=vpn";

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM });
  try {
    const context = await browser.newContext({ viewport: { width: 1120, height: 900 } });
    await context.addCookies([{name:"tpweb_token",value:"test-token",url}]);
    // OEM endpoints supply the page chrome; m7350l2 uses the actual host CGI.
    await context.route("**/cgi-bin/web_cgi", route => {
      const response = { result: 0, language: "en", factoryDefault: false, deviceInfo: { model: "M7350" },
        wan: {networkType:3,connectStatus:4,ipv4:"192.0.2.2",ipv6:"0.0.0.0",totalStatistics:0,dailyStatistics:0,
          txSpeed:0,rxSpeed:0,simStatus:3,signalStrength:3},
        wlan: {enable:true,ssid:"M7350-Test",supportWISP:false,disableWPS:false,securityMode:3},
        connectedDevices:{number:0},message:{unreadMessages:0},battery:{connected:false},
        oled:{supportOLED:true},sdcard:{supportSdcard:false}, mdLogState:2,totalNumber:0,logList:[]
      };
      return route.fulfill({json:response});
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", e => errors.push(e.stack));
    await page.goto(url + "/settings.html#Advanced/M7350VPN/M7350VPNMode");
    const panel = page.locator("#m7l2Failure");
    const reason = "PPP: VPN server rejected PAP/CHAP authentication";
    await panel.getByText(reason, {exact:true}).waitFor();
    assert.equal(await page.locator("#m7l2SwitchMsg").textContent(), "");
    assert.match(await panel.locator("time").innerText(), / UTC$/);
    const link = panel.getByRole("link", {name:"View VPN log"});
    assert.equal(await link.getAttribute("href"), target);
    assert.equal(await panel.locator("pre").count(), 0);
    assert.doesNotMatch(await panel.innerText(), /charon|swanctl|xl2tpd|pppd\.log/);
    if (evidence) await page.screenshot({path: path.join(evidence, "host-last-failure-panel.png")});
    await link.click();
    await page.getByText("pppd.log: CHAP authentication failed", {exact:true}).waitFor();
    assert.equal(await page.locator("#logTypeSelect").inputValue(), "7");
    assert.equal(await page.locator("#logTypeSelect + .dropdown-toggle").textContent(), "VPN");
    for (const [line, level] of [
      ["xl2tpd.log: xl2tpd started", "INFO"],
      ["swanctl-initiate.log: [CFG] selected proposal: IKE:AES_CBC_128/HMAC_SHA1_96/PRF_HMAC_SHA1/MODP_2048", "INFO"],
      ["swanctl-initiate.log: [IKE] IKE_SA m7350-l2tp[1] established", "INFO"],
      ["charon.log: 05[IKE] CHILD_SA l2tp{1} established", "INFO"],
      ["pppd.log: CHAP authentication failed", "ERROR"]
    ]) {
      const row = page.getByRole("row").filter({hasText:line});
      await row.getByRole("cell", {name:level, exact:true}).waitFor();
    }
    assert.equal(page.url().slice(-target.length), target);
    await page.waitForFunction(() => [...document.querySelectorAll("#ulM7350VPN .accordion-body")]
      .every(item => getComputedStyle(item).display === "none"));
    if (evidence) await page.screenshot({path: path.join(evidence, "host-system-log-vpn.png")});
    await page.goto(url + "/settings.html#Status");
    const card = page.locator("#m7350VpnStatus");
    await card.getByText("Failed: " + reason, {exact:true}).waitFor();
    const statusLink = card.getByRole("link", {name:"View VPN log"});
    assert.equal(await statusLink.getAttribute("href"), target);
    assert.doesNotMatch(await card.innerText(), /charon|swanctl|xl2tpd|pppd\.log/);
    await statusLink.click();
    await page.getByText("pppd.log: CHAP authentication failed", {exact:true}).waitFor();
    assert.equal(await page.locator("#logTypeSelect").inputValue(), "7");
    await page.reload();
    await page.getByText("pppd.log: CHAP authentication failed", {exact:true}).waitFor();
    await page.goto(url + "/settings.html#Advanced/Device/SysLog");
    await page.waitForFunction(() => Boolean(window.jQuery("#logTypeSelect").data("dropdown")));
    assert.equal(await page.locator("#logTypeSelect").inputValue(), "0");
    assert.deepEqual(errors, []);
    console.log("PASS: Operating Mode and Status summaries, VPN deep link, filtered extracts, direct reload and ordinary System Log.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode=1; });
