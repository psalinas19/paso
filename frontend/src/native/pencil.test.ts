import { expect, test, vi } from "vitest";
import { afterDoubleTap, isNative, onPencilDoubleTap } from "./pencil";

test("a double tap arms the one-shot eraser, and a second one gives the pen back", () => {
  expect(afterDoubleTap("pen", "pen")).toBe("eraser");
  expect(afterDoubleTap("lasso", "pen")).toBe("eraser");
  expect(afterDoubleTap("eraser", "highlighter")).toBe("highlighter");
});

test("outside the native app nothing listens and nothing breaks", () => {
  expect(isNative).toBe(false);
  const listener = vi.fn();
  const stop = onPencilDoubleTap(listener);
  stop();
  expect(listener).not.toHaveBeenCalled();
});
