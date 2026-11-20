import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Dialog } from "./Dialog.tsx";
import { PaneShell } from "./PaneShell.tsx";

function Harness({ removeTriggerOnClose = false, removeTriggerLater = false }: { removeTriggerOnClose?: boolean; removeTriggerLater?: boolean }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [triggerShown, setTriggerShown] = useState(true);
  return (
    <div>
      <aside data-testid="sidebar">
        <PaneShell title="Files">
          {triggerShown ? (
            <button type="button" onClick={() => setOpen(true)}>
              Open dialog
            </button>
          ) : null}
        </PaneShell>
      </aside>
      <main data-testid="main">
        <button type="button">Behind</button>
      </main>
      {open ? (
        <Dialog
          title="Sure?"
          onDismiss={() => setOpen(false)}
          actions={
            <>
              <button type="button" onClick={() => setOpen(false)}>
                Cancel
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  setBusy(true);
                }}
              >
                Confirm
              </button>
              <button
                type="button"
                onClick={() => {
                  if (removeTriggerOnClose) setTriggerShown(false);
                  // The tree of a confirmed delete re-renders after the dialog has gone.
                  if (removeTriggerLater) setTimeout(() => setTriggerShown(false), 0);
                  setOpen(false);
                }}
              >
                Finish
              </button>
            </>
          }
        >
          <label>
            Name
            <input />
          </label>
        </Dialog>
      ) : null}
    </div>
  );
}

async function openDialog() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open dialog" }));
  return user;
}

const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

describe("Dialog", () => {
  it("makes everything outside the dialog inert while it is open and restores it on close", async () => {
    render(<Harness />);
    expect(screen.getByTestId("main")).not.toHaveAttribute("inert");
    const user = await openDialog();
    expect(screen.getByTestId("main")).toHaveAttribute("inert");
    expect(screen.getByTestId("sidebar")).toHaveAttribute("inert");
    expect(screen.getByRole("dialog")).not.toHaveAttribute("inert");
    await user.keyboard("{Escape}");
    expect(screen.getByTestId("main")).not.toHaveAttribute("inert");
    expect(screen.getByTestId("sidebar")).not.toHaveAttribute("inert");
  });

  it("leaves a region that was already inert inert after closing", async () => {
    render(<Harness />);
    screen.getByTestId("main").setAttribute("inert", "");
    const user = await openDialog();
    await user.keyboard("{Escape}");
    expect(screen.getByTestId("main")).toHaveAttribute("inert");
  });

  it("moves focus to the first action when it opens and wraps Tab from the last control to the first", async () => {
    render(<Harness />);
    const user = await openDialog();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Confirm" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Finish" })).toHaveFocus();
    await user.tab();
    expect(screen.getByLabelText("Name")).toHaveFocus();
  });

  it("wraps Shift+Tab from the first control to the last", async () => {
    render(<Harness />);
    const user = await openDialog();
    screen.getByLabelText("Name").focus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Finish" })).toHaveFocus();
    await user.tab({ shift: true });
    await user.tab({ shift: true });
    await user.tab({ shift: true });
    expect(screen.getByLabelText("Name")).toHaveFocus();
  });

  it("keeps focus inside when the focused button becomes disabled and the browser drops focus", async () => {
    render(<Harness />);
    const user = await openDialog();
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    // A browser blurs a control that became disabled; jsdom does not, so it is done by hand.
    await act(async () => {
      (document.activeElement as HTMLElement).blur();
      await nextFrame();
    });
    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
    expect(document.activeElement).not.toBe(document.body);
    await user.tab();
    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
  });

  it("does not pull focus back while a native Tab is between blur and focus (real browsers leave the body focused for a moment)", async () => {
    render(<Harness />);
    await openDialog();
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const finish = screen.getByRole("button", { name: "Finish" });
    cancel.focus();
    await act(async () => {
      cancel.blur();
      // A microtask checkpoint runs between the blur and the focus of the next control.
      await Promise.resolve();
    });
    expect(cancel).not.toHaveFocus();
    await act(async () => {
      finish.focus();
      await nextFrame();
    });
    expect(finish).toHaveFocus();
  });

  it("does not let focus leave the dialog for an element behind it", async () => {
    render(<Harness />);
    await openDialog();
    await act(async () => {
      screen.getByRole("button", { name: "Behind" }).focus();
      await Promise.resolve();
    });
    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
  });

  it("returns focus to the element that opened it", async () => {
    render(<Harness />);
    const user = await openDialog();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Open dialog" })).toHaveFocus();
  });

  it("returns focus to the pane that held the trigger when the trigger was removed", async () => {
    render(<Harness removeTriggerOnClose />);
    const user = await openDialog();
    await user.click(screen.getByRole("button", { name: "Finish" }));
    expect(screen.queryByRole("button", { name: "Open dialog" })).toBeNull();
    expect(screen.getByRole("region", { name: "Files" })).toHaveFocus();
  });

  it("ends on a live element when the trigger is removed after the dialog has closed", async () => {
    render(<Harness removeTriggerLater />);
    const user = await openDialog();
    await user.click(screen.getByRole("button", { name: "Finish" }));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
      await nextFrame();
    });
    expect(screen.queryByRole("button", { name: "Open dialog" })).toBeNull();
    expect(document.body).not.toHaveFocus();
    expect(screen.getByRole("region", { name: "Files" })).toHaveFocus();
  });
});
