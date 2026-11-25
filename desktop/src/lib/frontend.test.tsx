import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { downsample, encodeWav, rms } from "./audio";
import { dictionaries, isRTL, translate } from "./i18n";
import { speechText } from "./tts";
import Markdown from "../components/Markdown";

describe("audio", () => {
  it("encodes a valid 16-bit PCM WAV header", () => {
    const buf = encodeWav(new Float32Array([0, 0.5, -0.5, 1]), 16000);
    const v = new DataView(buf);
    const tag = (o: number) => String.fromCharCode(...new Uint8Array(buf, o, 4));
    expect(tag(0)).toBe("RIFF");
    expect(tag(8)).toBe("WAVE");
    expect(v.getUint32(24, true)).toBe(16000);
    expect(v.getUint16(34, true)).toBe(16);
    expect(v.getUint32(40, true)).toBe(8);
    expect(v.getInt16(46, true)).toBe(16383);
    expect(v.getInt16(50, true)).toBe(32767);
  });
  it("downsamples 48k -> 16k", () => {
    expect(downsample(new Float32Array(48000), 48000).length).toBe(16000);
  });
  it("computes rms", () => {
    expect(rms(new Float32Array([1, -1, 1, -1]))).toBeCloseTo(1);
  });
});

describe("i18n", () => {
  it("Hebrew dictionary covers every English key", () => {
    const missing = Object.keys(dictionaries.en).filter((k) => !(k in dictionaries.he));
    expect(missing).toEqual([]);
  });
  it("interpolates variables", () => {
    expect(translate("en", "confirm.expires", { s: 5 })).toBe("Auto-denies in 5s");
  });
  it("detects RTL text by first strong character", () => {
    expect(isRTL("שלום world")).toBe(true);
    expect(isRTL("hello עולם")).toBe(false);
    expect(isRTL("123")).toBe(false);
  });
});

describe("markdown", () => {
  it("never injects raw HTML", () => {
    const { container } = render(<Markdown text={'<img src=x onerror="alert(1)"> **bold** `code`'} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelector("code")?.textContent).toBe("code");
  });
  it("renders code fences, lists and only http(s) links", () => {
    const { container } = render(<Markdown text={"- a\n- b\n\n```py\nprint(1)\n```\n[ok](https://x.dev) [bad](javascript:alert(1))"} />);
    expect(container.querySelectorAll("li").length).toBe(2);
    expect(container.querySelector("pre")?.textContent).toBe("print(1)");
    const links = Array.from(container.querySelectorAll("a"));
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["https://x.dev"]);
  });
});

describe("tts", () => {
  it("strips markdown and code before speaking", () => {
    expect(speechText("**Done** ✅\n```js\nx()\n```\nSee [docs](https://a.b)")).toBe("Done See docs");
  });
});
