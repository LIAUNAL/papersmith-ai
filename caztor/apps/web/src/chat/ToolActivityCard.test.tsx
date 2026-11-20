import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ChatItem } from "@caztor/core";
import { ToolActivityCard } from "./ToolActivityCard.tsx";

type Tool = Extract<ChatItem, { kind: "tool" }>;
const tool = (patch: Partial<Tool> = {}): Tool => ({ kind: "tool", toolId: "x", name: "Edit", toolKind: "edit", status: "running", ...patch });

describe("ToolActivityCard", () => {
  it.each([
    ["running", "Running"],
    ["done", "Done"],
    ["failed", "Failed"],
    ["interrupted", "Interrupted"],
  ] as const)("shows the %s state as text, not only as color", (status, label) => {
    render(<ToolActivityCard tool={tool({ status })} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("names the tool and the file it touched in a path chip", () => {
    render(<ToolActivityCard tool={tool({ name: "Edit", path: "sections/intro.tex", status: "done" })} />);
    expect(screen.getByText("Edit")).toBeInTheDocument();
    const chip = screen.getByText("sections/intro.tex");
    expect(chip.closest(".tool-card__path")).not.toBeNull();
  });

  it("is a collapsed group whose details show the title and summary only when opened", async () => {
    render(<ToolActivityCard tool={tool({ status: "done", title: "Replaced the title", summary: "1 change" })} />);
    const toggle = screen.getByRole("button", { name: /Edit/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("1 change")).toBeNull();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("1 change")).toBeInTheDocument();
    expect(screen.getByText("Replaced the title")).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(screen.queryByText("1 change")).toBeNull();
  });

  it("has nothing to open when the tool gave no details", () => {
    render(<ToolActivityCard tool={tool({ status: "done" })} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("never shows raw JSON", () => {
    const { container } = render(<ToolActivityCard tool={tool({ path: "a.tex" })} />);
    expect(container.textContent).not.toMatch(/[{}"]/);
  });
});
