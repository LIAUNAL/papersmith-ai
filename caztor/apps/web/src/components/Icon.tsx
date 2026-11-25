import type { ReactNode } from "react";

export type IconName = "file" | "folder" | "file-plus" | "folder-plus" | "upload" | "pencil" | "trash" | "chevron" | "play" | "stop" | "zoom-in" | "zoom-out" | "fit-width" | "alert" | "send" | "undo" | "refresh" | "plus" | "check" | "x";

const PATHS: Record<IconName, ReactNode> = {
  file: <path d="M4 1.75h5.5L13 5.25v9H4zM9.5 1.75v3.5H13" />,
  folder: <path d="M1.75 3.75h4l1.5 1.5h7v8h-12.5z" />,
  "file-plus": <path d="M4 1.75h5.5L13 5.25v9H4zM9.5 1.75v3.5H13M8.5 8v4M6.5 10h4" />,
  "folder-plus": <path d="M1.75 3.75h4l1.5 1.5h7v8h-12.5zM8 7.5v4M6 9.5h4" />,
  upload: <path d="M8 10.5v-8M4.75 5.5 8 2.25l3.25 3.25M2.5 10.5v3h11v-3" />,
  pencil: <path d="m10.5 2.5 3 3-8 8H2.5v-3zM9 4l3 3" />,
  trash: <path d="M2.5 4.25h11M6 4.25v-2h4v2M4 4.25l.5 9.5h7l.5-9.5M6.75 7v4.5M9.25 7v4.5" />,
  chevron: <path d="m6 3.5 4.5 4.5L6 12.5" />,
  play: <path d="M4.5 2.75v10.5l8.5-5.25z" />,
  stop: <path d="M3.75 3.75h8.5v8.5h-8.5z" />,
  "zoom-in": <path d="M7 11.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9zM10.25 10.25l3.5 3.5M7 5v4M5 7h4" />,
  "zoom-out": <path d="M7 11.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9zM10.25 10.25l3.5 3.5M5 7h4" />,
  "fit-width": <path d="M2 3v10M14 3v10M4.5 8h7M6.5 6l-2 2 2 2M9.5 6l2 2-2 2" />,
  alert: <path d="M8 2 14.25 13.25H1.75zM8 6.5v3M8 11.25v.01" />,
  send: <path d="M2.25 8 13.75 2.5 11 13.5 8.25 9.25zM8.25 9.25l5.5-6.75" />,
  undo: <path d="M5.5 3 2.5 6l3 3M2.75 6H10a3.5 3.5 0 0 1 0 7H6.5" />,
  refresh: <path d="M13 8a5 5 0 1 1-1.5-3.55M13 2.5v3h-3" />,
  plus: <path d="M8 3v10M3 8h10" />,
  check: <path d="m3 8.5 3.25 3.25L13 4.75" />,
  x: <path d="m4 4 8 8M12 4l-8 8" />,
};

interface IconProps {
  name: IconName;
  className?: string;
}

/** A 16 px line icon that takes the text color. Decorative: the button around it carries the label. */
export function Icon({ name, className }: IconProps) {
  return (
    <svg
      className={className}
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
