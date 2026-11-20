import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NoticeBanner } from "./NoticeBanner.tsx";

describe("NoticeBanner", () => {
  it("shows the message for info and warning notices", () => {
    const { rerender, container } = render(<NoticeBanner level="info" message="New conversation started." />);
    expect(screen.getByText("New conversation started.")).toBeInTheDocument();
    expect(container.querySelector(".notice--info")).not.toBeNull();
    rerender(<NoticeBanner level="warning" message="Careful." />);
    expect(container.querySelector(".notice--warning")).not.toBeNull();
  });

  it("offers the replace action only when the notice carries it, and asks first", async () => {
    const onReplace = vi.fn();
    const { rerender } = render(<NoticeBanner level="warning" message="Plain." onReplace={onReplace} />);
    expect(screen.queryByRole("button")).toBeNull();
    rerender(<NoticeBanner level="warning" message="You changed the definition." action="replace_definition" onReplace={onReplace} />);
    await userEvent.click(screen.getByRole("button", { name: "Replace definition" }));
    expect(onReplace).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog", { name: "Replace the agent definition?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(onReplace).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Replace definition" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Replace" }));
    expect(onReplace).toHaveBeenCalledTimes(1);
  });
});
