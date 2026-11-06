"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Group, Panel, Separator, useDefaultLayout, type GroupImperativeHandle, type PanelImperativeHandle } from "react-resizable-panels";
import type { ClientMessage, StateView } from "@/lib/nightwire/protocol";
import { browserStore, readFlag, writeFlag } from "@/lib/nightwire/safeStorage";
import { sceneImages } from "@/lib/nightwire/feed";
import { FeedPanel } from "./FeedPanel";
import { GalleryOverlay } from "./GalleryOverlay";
import { Rail } from "./Rail";
import { StatusPanel } from "./StatusPanel";
import { WorldPanel } from "./WorldPanel";
import "./play.css";

const RAIL_PX = 28;
const SCENE_ART_KEY = "nightwire-scene-art";
const NARROW = "(max-width: 1023.98px)";
const TABS = ["feed", "status", "world"] as const;

function subscribeNarrow(onChange: () => void) {
  const query = window.matchMedia(NARROW);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export function PlayScreen({ view, playerId, send, readyLabel, error, errorSeq }: {
  view: StateView;
  playerId: string;
  send: (msg: ClientMessage) => void;
  readyLabel: string;
  error: string | null;
  errorSeq: number;
}) {
  const { defaultLayout, onLayoutChanged } = useDefaultLayout({ id: "nightwire-play", storage: browserStore });
  const groupRef = useRef<GroupImperativeHandle>(null);
  const statusRef = useRef<PanelImperativeHandle>(null);
  const worldRef = useRef<PanelImperativeHandle>(null);
  const [statusCollapsed, setStatusCollapsed] = useState(false);
  const [worldCollapsed, setWorldCollapsed] = useState(true);
  const [beforeImmersive, setBeforeImmersive] = useState<Record<string, number> | null>(null);
  const immersive = beforeImmersive !== null;
  // The play screen only mounts after a websocket view arrives, so this never runs during server rendering.
  const [sceneArt, setSceneArt] = useState(() => readFlag(browserStore, SCENE_ART_KEY, true));
  const [galleryIndex, setGalleryIndex] = useState<number | null>(null);
  const images = sceneImages(view.log);
  const narrow = useSyncExternalStore(subscribeNarrow, () => window.matchMedia(NARROW).matches, () => false);
  const [tab, setTab] = useState<(typeof TABS)[number]>("feed");

  function toggleSceneArt() {
    writeFlag(browserStore, SCENE_ART_KEY, !sceneArt);
    setSceneArt(!sceneArt);
  }

  function resetLayout() {
    setBeforeImmersive(null);
    statusRef.current?.expand();
    statusRef.current?.resize("20");
    worldRef.current?.collapse();
  }

  function toggleImmersive() {
    if (beforeImmersive) {
      groupRef.current?.setLayout(beforeImmersive);
      setBeforeImmersive(null);
    } else {
      setBeforeImmersive(groupRef.current?.getLayout() ?? null);
      statusRef.current?.collapse();
      worldRef.current?.collapse();
    }
  }

  // Ctrl/Cmd+K used to open the sheet pop-over; the sheet now lives in the Status panel.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        const panel = statusRef.current;
        if (panel?.isCollapsed()) panel.expand();
        else panel?.collapse();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const watchCollapsed = (set: (collapsed: boolean) => void) => (size: { inPixels: number }) => set(size.inPixels <= RAIL_PX + 1);

  return (
    <div className="nw-play flex h-dvh w-full flex-col">
      <header className="nw-play-header">
        <span style={{ color: "var(--nw-cyan)", fontWeight: 700, letterSpacing: ".22em" }}>NIGHTWIRE</span>
        <span className="flex-1" />
        <button type="button" className="nw-chip" aria-pressed={sceneArt} onClick={toggleSceneArt}>Scene art {sceneArt ? "on" : "off"}</button>
        <button type="button" className="nw-chip" disabled={images.length === 0} onClick={() => setGalleryIndex(images.length - 1)}>Gallery · {images.length}</button>
        {!narrow && (
          <>
            <button type="button" className="nw-chip" aria-pressed={immersive} onClick={toggleImmersive}>Immersive view</button>
            <button type="button" className="nw-chip" onClick={resetLayout}>Reset layout</button>
          </>
        )}
        <span className="nw-chip" style={{ cursor: "default" }} role="status">{readyLabel}</span>
      </header>
      {narrow ? (
        <>
          <div className="min-h-0 flex-1">
            {tab === "feed" && <FeedPanel view={view} playerId={playerId} send={send} error={error} errorSeq={errorSeq} sceneArt={sceneArt} onOpenGallery={setGalleryIndex} compact />}
            {tab === "status" && <StatusPanel view={view} playerId={playerId} send={send} />}
            {tab === "world" && <WorldPanel view={view} playerId={playerId} />}
          </div>
          <nav aria-label="Panels" className="nw-tabs">
            {TABS.map((t) => (
              <button key={t} type="button" aria-current={tab === t ? "page" : undefined} onClick={() => setTab(t)}>{t.toUpperCase()}</button>
            ))}
          </nav>
        </>
      ) : (
      <Group orientation="horizontal" groupRef={groupRef} defaultLayout={defaultLayout} onLayoutChanged={onLayoutChanged} className="min-h-0 flex-1">
        <Panel id="status" panelRef={statusRef} defaultSize="20" minSize="14" collapsible collapsedSize={RAIL_PX} onResize={watchCollapsed(setStatusCollapsed)}>
          {statusCollapsed
            ? <Rail label="Status" side="left" onOpen={() => statusRef.current?.expand()} />
            : <StatusPanel view={view} playerId={playerId} send={send} />}
        </Panel>
        <Separator className="nw-separator" aria-label="Resize status panel" />
        <Panel id="feed" defaultSize="58" minSize="40">
          <FeedPanel view={view} playerId={playerId} send={send} error={error} errorSeq={errorSeq} sceneArt={sceneArt} onOpenGallery={setGalleryIndex} />
        </Panel>
        <Separator className="nw-separator" aria-label="Resize world panel" />
        <Panel id="world" panelRef={worldRef} defaultSize={RAIL_PX} minSize="14" collapsible collapsedSize={RAIL_PX} onResize={watchCollapsed(setWorldCollapsed)}>
          {worldCollapsed
            ? <Rail label="Party" side="right" onOpen={() => worldRef.current?.expand()} />
            : <WorldPanel view={view} playerId={playerId} />}
        </Panel>
      </Group>
      )}
      <GalleryOverlay images={images} openIndex={galleryIndex} onClose={() => setGalleryIndex(null)} />
    </div>
  );
}
