// The SC-001 "< 50 LoC consumer code" reference implementation.
//
// The example consumes `@aivg/sat-sdk` via the workspace path. In a
// downstream project you'd `npm install @aivg/sat-sdk` and import from
// the package name.
import { Satellite } from "../../src/index";

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;
const log = (s: string): void => {
  const el = $<HTMLPreElement>("log");
  el.textContent = `${el.textContent ?? ""}${s}\n`;
};

const sat = new Satellite({
  gatewayUrl: ($<HTMLInputElement>("gw")).value,
  deviceId: localStorage.getItem("aivg-browser-ptt-id") ?? crypto.randomUUID(),
  deviceName: "browser-ptt-demo",
  deviceType: "browser",
});
localStorage.setItem("aivg-browser-ptt-id", sat.options.deviceId);

sat.on("adoption", (e) => ($<HTMLElement>("adoption").textContent = e.state));
sat.on("state", (e) => ($<HTMLElement>("state").textContent = e.current));
sat.on("transcript", (d) => log(`${d.speaker}: ${d.text}`));
sat.on("log", (e) => log(`[${e.level}] ${e.source}: ${e.message}`));
sat.on("error", (e) => log(`! ${e.code}: ${e.message}`));
sat.on("transient_error", (e) => log(`~ ${e.code}: ${e.message} (retry in ${e.retryInMs}ms)`));

$<HTMLButtonElement>("connect").addEventListener("click", () => {
  sat.connect().catch((e: unknown) => log(`connect failed: ${String(e)}`));
});
$<HTMLButtonElement>("disconnect").addEventListener("click", () => void sat.disconnect());
$<HTMLButtonElement>("ptt-down").addEventListener("mousedown", () => {
  sat.beginSession().catch((e: unknown) => log(`beginSession failed: ${String(e)}`));
});
$<HTMLButtonElement>("ptt-up").addEventListener("mouseup", () => void sat.endSession());
