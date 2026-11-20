import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { ApiClient, FileContent, Session } from "../api/types.ts";
import { EditorPane } from "../editor/EditorPane.tsx";
import { EditorSession } from "../editor/session.ts";
import { Dialog } from "../components/Dialog.tsx";
import { DisclosureNotice } from "../disclosure/DisclosureNotice.tsx";
import { FileTree } from "../files/FileTree.tsx";
import { Workspace } from "../layout/Workspace.tsx";
import type { LayoutStore } from "../layout/storage.ts";
import { ChatController } from "../chat/controller.ts";
import { ChatPanel } from "../chat/ChatPanel.tsx";
import { startAutoCompile } from "../compile/auto-compile.ts";
import { CompileController } from "../compile/controller.ts";
import { CompileToolbar } from "../compile/CompileToolbar.tsx";
import { useSettings } from "../compile/useSettings.ts";
import type { PdfEngine } from "../preview/engine.ts";
import { pdfjsEngine } from "../preview/engine-pdfjs.ts";
import { createPrefsStore } from "../preview/prefs.ts";
import { PreviewPane } from "../preview/PreviewPane.tsx";
import type { StorageLike } from "../layout/storage.ts";
import { ProjectRail } from "../projects/ProjectRail.tsx";
import { listenForCompose, listenForTheme, postReady, postSelection } from "../embed/bridge.ts";
import { useExplained } from "../explain/useExplained.ts";
import { createThemeStore, type ThemeStore } from "../theme/theme.ts";
import { ThemeControl } from "../theme/ThemeControl.tsx";
import { CollaboratorsDialog } from "../users/CollaboratorsDialog.tsx";
import "./App.css";

interface AppProps {
  api: ApiClient;
  layoutStore: LayoutStore;
  /** Where zoom and scroll position of the preview are remembered; null: not remembered. */
  previewStorage?: StorageLike | null;
  /** Draws PDFs. Tests replace it; the default is PDF.js. */
  pdfEngine?: PdfEngine;
  /** The chosen color theme. By default nothing is remembered. */
  themeStore?: ThemeStore;
  /** Starts the page again on the project the server moved to. Tests replace it. */
  reloadPage?: () => void;
}

type Load = { state: "loading" } | { state: "failed"; message: string } | { state: "ready"; session: Session };

/** The application frame: a slim header, the four-pane workspace and the first-use notice. */
export function App({ api, layoutStore, previewStorage = null, pdfEngine = pdfjsEngine, themeStore, reloadPage = () => window.location.reload() }: AppProps) {
  const [theme] = useState(() => themeStore ?? createThemeStore(null));
  const [load, setLoad] = useState<Load>({ state: "loading" });

  const open = useCallback(() => {
    setLoad({ state: "loading" });
    api.getSession().then(
      (session) => setLoad({ state: "ready", session }),
      (error: unknown) => setLoad({ state: "failed", message: error instanceof Error ? error.message : "The project could not be opened." }),
    );
  }, [api]);

  useEffect(open, [open]);

  if (load.state === "loading") {
    return (
      <div className="app app--centered" role="status">
        Opening project
      </div>
    );
  }
  if (load.state === "failed") {
    return (
      <div className="app app--centered">
        <div role="alert" className="app__failure">
          <p>{load.message}</p>
          <button type="button" className="button" onClick={open}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <Project
      api={api}
      layoutStore={layoutStore}
      previewStorage={previewStorage}
      pdfEngine={pdfEngine}
      theme={theme}
      reloadPage={reloadPage}
      session={load.session}
      onAcknowledged={(settings) => setLoad({ state: "ready", session: { ...load.session, settings } })}
    />
  );
}

interface ProjectProps {
  api: ApiClient;
  layoutStore: LayoutStore;
  previewStorage: StorageLike | null;
  pdfEngine: PdfEngine;
  theme: ThemeStore;
  reloadPage: () => void;
  session: Session;
  onAcknowledged: (settings: Session["settings"]) => void;
}

/** An open project: the header, the panes and the first-use notice. */
function Project({ api, layoutStore, previewStorage, pdfEngine, theme, reloadPage, session: projectSession, onAcknowledged }: ProjectProps) {
  const [session] = useState(() => new EditorSession({ api }));
  const editing = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const [compiler] = useState(() => new CompileController({ api }));
  const compile = useSyncExternalStore(compiler.subscribe, compiler.getSnapshot);
  const [chat] = useState(() => new ChatController({ api }));
  const { settings, change } = useSettings(api, projectSession.settings);
  const prefs = useMemo(() => createPrefsStore(previewStorage, projectSession.project.name), [previewStorage, projectSession.project.name]);

  const reload = useRef(reloadPage);
  reload.current = reloadPage;

  // Changes made outside the editor (an agent, another program) and compile progress arrive as events; a reconnect may have missed some.
  useEffect(
    () =>
      api.subscribeEvents((event) => {
        if (event.event === "project_changed") reload.current();
        void session.handleEvent(event);
        compiler.handleEvent(event);
      }),
    [api, session, compiler],
  );
  useEffect(() => void compiler.refresh(), [compiler]);
  // A collaborator's chat is their own: their history, choices, keys and sign-ins, and turns in their sandbox on the host.
  const user = projectSession.user;
  const [showingCollaborators, setShowingCollaborators] = useState(false);
  useEffect(() => {
    void chat.load();
  }, [chat]);

  // The passages the latest reply explains, marked in the editor and the PDF while the chat's switch is on.
  const explained = useExplained(chat, previewStorage);
  const highlights = explained.on ? explained.passages : [];

  // Shown inside a PaperSmith dashboard: its change-control panel sends text for the chat box and hears PDF selections.
  const embedOrigin = projectSession.embed?.origin;
  useEffect(() => (embedOrigin === undefined ? undefined : listenForCompose(embedOrigin, (text) => void chat.compose(text))), [embedOrigin, chat]);
  // The dashboard owns the theme: Caztor listens first, then says it is ready, and the dashboard answers with its theme.
  useEffect(() => {
    if (embedOrigin === undefined) return;
    const stop = listenForTheme(embedOrigin, (next) => theme.set(next));
    postReady(embedOrigin);
    return stop;
  }, [embedOrigin, theme]);

  // Compile shortly after each successful save while the switch is on.
  const current = useRef({ autoCompile: settings.autoCompile, engine: projectSession.engine.available });
  current.current = { autoCompile: settings.autoCompile, engine: projectSession.engine.available };
  useEffect(
    () =>
      startAutoCompile({
        onSaved: (listener) => session.onSaved(listener),
        isEnabled: () => current.current.autoCompile && current.current.engine,
        compile: () => void compiler.start(),
      }),
    [session, compiler],
  );

  // Leaving the page with an edit that is not saved yet asks the browser to confirm.
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if ([...session.getSnapshot().buffers.values()].some((buffer) => buffer.status !== "saved")) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      void session.flushAll();
    };
  }, [session]);

  const openFile = (file: FileContent) => {
    session.open(file);
    session.setActive(file.path);
  };

  /** Opens a file and puts the cursor on a line. A file that is already open keeps its unsaved text. */
  async function openAt(path: string, line: number): Promise<string | null> {
    try {
      if (session.get(path) === undefined) session.open(await api.readFile(path));
      session.setActive(path);
      session.reveal(path, line);
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : `${path} could not be opened.`;
    }
  }

  // Read again after something that changes how a project is listed, such as creating its paper.
  const [projectsSeen, setProjectsSeen] = useState(0);
  const listProjects = useCallback(() => api.listProjects(), [api, projectsSeen]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Saves what is open, then moves the server. Nothing moves unless every edit reached the disk. */
  const openProject = (path: string) => leaveFor(() => api.openProject(path));
  const createProject = (name: string) => leaveFor(() => api.createProject(name));

  async function leaveFor(move: () => Promise<unknown>): Promise<string | null> {
    try {
      await session.flushAll();
      if ([...session.getSnapshot().buffers.values()].some((buffer) => buffer.status !== "saved")) {
        return "Some edits could not be saved. Resolve them before opening another project.";
      }
      await move();
      reloadPage();
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : "The project could not be opened.";
    }
  }

  // A PaperSmith workspace has one known paper: open it, or offer to create it the way PaperSmith does.
  const papersmith = projectSession.papersmith;
  const [askingForMain, setAskingForMain] = useState(papersmith?.exists === false);
  const [mainProblem, setMainProblem] = useState<string | null>(null);
  useEffect(() => {
    if (papersmith?.exists === true && session.getSnapshot().active === null) void openAt(papersmith.main, 1);
    // Only when the project opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createMain(): Promise<void> {
    if (papersmith === undefined) return;
    try {
      await api.scaffoldPaper();
      setAskingForMain(false);
      setProjectsSeen((seen) => seen + 1);
      const problem = await openAt(papersmith.main, 1);
      if (problem !== null) setMainProblem(problem);
    } catch (error) {
      setMainProblem(error instanceof Error ? error.message : "The paper could not be created.");
    }
  }

  async function acknowledge(): Promise<void> {
    onAcknowledged(await api.patchSettings({ disclosureAcknowledged: true }));
  }

  return (
    <div className="app">
      {embedOrigin !== undefined ? null : (
        <header className="app__bar">
          <span className="app__brand">Caztor</span>
          <span className="app__project">{projectSession.project.name}</span>
          {user === undefined ? null : <span className="app__user">{user.name}</span>}
          {user?.role === "host" ? (
            <button type="button" className="button app__collaborators" onClick={() => setShowingCollaborators(true)}>
              Collaborators
            </button>
          ) : null}
          <ThemeControl store={theme} />
        </header>
      )}
      <div className="app__body">
        {embedOrigin === undefined ? <ProjectRail list={listProjects} onOpen={openProject} onCreate={createProject} storage={previewStorage} /> : null}
        <main className="app__main">
          <Workspace
            layoutStore={layoutStore}
            headers={{
              preview: (
                <CompileToolbar
                  state={compile}
                  engine={projectSession.engine}
                  onCompile={() => void compiler.start()}
                  onCancel={() => void compiler.cancel()}
                  currentFile={editing.active}
                  mainFile={settings.mainFile}
                  onCompileFile={(path) => void compiler.start(path)}
                />
              ),
            }}
            content={{
              files: (
                <FileTree
                  api={api}
                  selectedPath={editing.active}
                  onOpen={openFile}
                  onRenamed={(from, to) => session.rename(from, to)}
                  onDeleted={(path) => session.forget(path)}
                />
              ),
              preview: (
                <PreviewPane
                  api={api}
                  engine={pdfEngine}
                  engineStatus={projectSession.engine}
                  sandboxStatus={projectSession.sandbox}
                  compile={compile}
                  settings={settings}
                  onSettingsChange={change}
                  prefs={prefs}
                  onOpenDiagnostic={openAt}
                  highlights={highlights}
                  focus={explained.on ? explained.focus : null}
                  {...(embedOrigin === undefined ? {} : { onTextSelected: (selection) => postSelection(embedOrigin, selection) })}
                />
              ),
              chat: (
                <ChatPanel
                  controller={chat}
                  onOpenFile={(path) => void openAt(path, 1)}
                  onCompile={() => void compiler.start()}
                  explain={{ on: explained.on, count: explained.passages.length, onToggle: explained.toggle, current: explained.current, onStep: explained.step }}
                />
              ),
              ...(editing.active === null ? {} : { editor: <EditorPane session={session} highlights={highlights} focus={explained.on ? explained.focus : null} /> }),
            }}
          />
        </main>
      </div>
      {projectSession.settings.disclosureAcknowledged ? null : <DisclosureNotice onAcknowledge={acknowledge} />}
      {showingCollaborators ? <CollaboratorsDialog api={api} onClose={() => setShowingCollaborators(false)} /> : null}
      {projectSession.settings.disclosureAcknowledged && askingForMain && papersmith !== undefined ? (
        <Dialog
          title={`Create ${papersmith.main}?`}
          onDismiss={() => setAskingForMain(false)}
          actions={
            <>
              <button type="button" className="button" onClick={() => setAskingForMain(false)}>
                Not now
              </button>
              <button type="button" className="button button--primary" onClick={() => void createMain()}>
                Create
              </button>
            </>
          }
        >
          <p>
            This PaperSmith workspace has no paper yet. Caztor can create it the way PaperSmith&apos;s scaffold does, with{" "}
            <code>paper/refs.bib</code> and a <code>paper/Figures/</code> folder, and with <code>{papersmith.main}</code> as a short
            document that compiles. Nothing that exists is changed. PaperSmith then adds the paper block by block.
          </p>
          {mainProblem === null ? null : <p role="alert">{mainProblem}</p>}
        </Dialog>
      ) : null}
    </div>
  );
}
