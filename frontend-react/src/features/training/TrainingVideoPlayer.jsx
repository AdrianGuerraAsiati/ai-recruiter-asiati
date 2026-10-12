// eslint-disable-next-line no-unused-vars
import React, { useEffect, useRef, useState } from "react";

import { ProgressBar } from "../../components/ui/StatePanel";
import { isDirectVideo } from "./trainingUtils";

const SEGMENT_SECONDS = 20;
const SAVE_INTERVAL_SECONDS = 5;
const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

export default function TrainingVideoPlayer({
  lesson,
  onVideoProgress,
  onRefreshVideoUrl,
  onSaveOnExit,
}) {
  const videoRef = useRef(null);
  // A signed URL changes whenever progress is saved. Retain it until an
  // actual playback failure or an explicit refresh, not on every API response.
  const [playbackUrl, setPlaybackUrl] = useState(() => lesson.video_url);
  const [speed, setSpeed] = useState(1);
  const [recovering, setRecovering] = useState(false);
  const [videoError, setVideoError] = useState("");

  const callbacksRef = useRef({ lesson, onVideoProgress, onRefreshVideoUrl, onSaveOnExit });
  const pendingRef = useRef([]);
  const drainingRef = useRef(false);
  const segmentStartRef = useRef(null);
  const lastObservedRef = useRef(null);
  const durationRef = useRef(Number(lesson.duration_seconds) || 0);
  const playbackUrlRef = useRef(lesson.video_url);
  const loadedMetadataRef = useRef(false);
  const restorePositionRef = useRef(null);
  const resumeAfterRecoveryRef = useRef(false);
  const wasPlayingRef = useRef(false);
  const recoveringRef = useRef(false);
  const automaticRetriesRef = useRef(0);
  const saveOnExitRef = useRef(null);
  const watchedPercent = Number(lesson.video_progress?.watched_percent || 0);
  const threshold = Number(lesson.video_progress?.completion_threshold_percent || 80);
  const managedVideo = lesson.video_source === "managed";

  useEffect(() => {
    callbacksRef.current = { lesson, onVideoProgress, onRefreshVideoUrl, onSaveOnExit };
  }, [lesson, onVideoProgress, onRefreshVideoUrl, onSaveOnExit]);

  async function drainSegments() {
    if (drainingRef.current) return;
    drainingRef.current = true;
    try {
      while (pendingRef.current.length > 0) {
        const segment = pendingRef.current[0];
        const { lesson: activeLesson, onVideoProgress: save } = callbacksRef.current;
        let response = null;
        try {
          response = await save(activeLesson, segment);
        } catch {
          // Preserve unsent ranges. The next playback event can retry them.
        }
        if (response == null) break;
        pendingRef.current.shift();
      }
    } finally {
      drainingRef.current = false;
    }
  }

  function queueWatchedTime(endTime) {
    const start = segmentStartRef.current;
    const end = Number(endTime);
    if (start == null || !Number.isFinite(end) || end <= start + 0.25) return;

    // The backend rejects segments longer than 30 seconds. Split gaps
    // caused by background tabs into small, sequential, idempotent ranges.
    const duration = durationRef.current || Number(callbacksRef.current.lesson.duration_seconds) || 0;
    let from = start;
    while (end - from > 0.25) {
      const to = Math.min(from + SEGMENT_SECONDS, end);
      pendingRef.current.push({
        duration_seconds: duration,
        played_from_seconds: from,
        played_to_seconds: to,
        position_seconds: to,
      });
      from = to;
    }
    segmentStartRef.current = end;
    void drainSegments();
  }

  function flushCurrentSegment({ keepalive = false } = {}) {
    const last = lastObservedRef.current;
    if (last != null) queueWatchedTime(last);
    if (keepalive && callbacksRef.current.onSaveOnExit) {
      // Browser navigation can abort ordinary Axios requests. Keepalive
      // covers recent queued segments without relying on unload promises.
      for (const segment of pendingRef.current.slice(-3)) {
        try {
          callbacksRef.current.onSaveOnExit(callbacksRef.current.lesson, segment);
        } catch {
          // Best effort; regular periodic saves remain the primary mechanism.
        }
      }
    }
    void drainSegments();
  }

  useEffect(() => {
    saveOnExitRef.current = flushCurrentSegment;
  });

  useEffect(() => {
    const onHidden = () => {
      if (document.visibilityState === "hidden") {
        saveOnExitRef.current?.({ keepalive: true });
      }
    };
    const onPageHide = () => saveOnExitRef.current?.({ keepalive: true });
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("pagehide", onPageHide);
      saveOnExitRef.current?.();
    };
  }, []);

  function handleLoadedMetadata(event) {
    if (loadedMetadataRef.current) return;
    loadedMetadataRef.current = true;
    const video = event.currentTarget;
    const duration = Number(video.duration);
    if (Number.isFinite(duration) && duration > 0) durationRef.current = duration;
    video.playbackRate = speed;

    const position = restorePositionRef.current
      ?? Number(callbacksRef.current.lesson.video_progress?.last_position_seconds || 0);
    restorePositionRef.current = null;
    if (Number.isFinite(duration) && duration > 0
      && Number.isFinite(position) && position > 0
      && position < duration - 1) {
      video.currentTime = position;
    }
    if (resumeAfterRecoveryRef.current) {
      resumeAfterRecoveryRef.current = false;
      // Mobile browsers may require another user gesture; leave play enabled.
      const attempt = video.play();
      if (attempt?.catch) void attempt.catch(() => {});
    }
  }

  function handlePlay(event) {
    wasPlayingRef.current = true;
    const current = Number(event.currentTarget.currentTime || 0);
    segmentStartRef.current = current;
    lastObservedRef.current = current;
    void drainSegments();
  }

  function handleTimeUpdate(event) {
    const current = Number(event.currentTarget.currentTime || 0);
    if (segmentStartRef.current == null) {
      if (!event.currentTarget.paused) segmentStartRef.current = current;
    } else if (!event.currentTarget.paused
      && current - segmentStartRef.current >= SAVE_INTERVAL_SECONDS) {
      queueWatchedTime(current);
    }
    lastObservedRef.current = current;
  }

  function handleSeeking() {
    // A seek must not be credited as watched video time.
    if (lastObservedRef.current != null) queueWatchedTime(lastObservedRef.current);
    segmentStartRef.current = null;
    lastObservedRef.current = null;
  }

  function handleSeeked(event) {
    const current = Number(event.currentTarget.currentTime || 0);
    segmentStartRef.current = current;
    lastObservedRef.current = current;
  }

  function handlePause(event) {
    wasPlayingRef.current = false;
    lastObservedRef.current = Number(event.currentTarget.currentTime || 0);
    flushCurrentSegment();
  }

  function handleEnded(event) {
    wasPlayingRef.current = false;
    lastObservedRef.current = Number(event.currentTarget.currentTime || 0);
    flushCurrentSegment();
  }

  async function recoverVideo(automatic = false) {
    const { lesson: activeLesson, onRefreshVideoUrl: refresh } = callbacksRef.current;
    if (!managedVideo || !refresh) {
      setVideoError("No se pudo reproducir el video. Contacta a Talento Humano.");
      return;
    }
    if (recoveringRef.current || (automatic && automaticRetriesRef.current >= 2)) {
      if (automatic && automaticRetriesRef.current >= 2) {
        setVideoError("No fue posible cargar el video. Pulsa Reintentar.");
      }
      return;
    }
    if (automatic) automaticRetriesRef.current += 1;
    recoveringRef.current = true;
    setRecovering(true);
    setVideoError("");
    const video = videoRef.current;
    const position = Number(video?.currentTime ?? lastObservedRef.current
      ?? activeLesson.video_progress?.last_position_seconds ?? 0);
    const shouldResume = wasPlayingRef.current && !video?.ended;
    flushCurrentSegment();
    try {
      const newUrl = await refresh(activeLesson);
      if (!isDirectVideo(newUrl) || newUrl === playbackUrlRef.current) {
        throw new Error("The server did not return a fresh playable URL.");
      }
      restorePositionRef.current = position;
      resumeAfterRecoveryRef.current = shouldResume;
      loadedMetadataRef.current = false;
      segmentStartRef.current = null;
      lastObservedRef.current = null;
      playbackUrlRef.current = newUrl;
      setPlaybackUrl(newUrl);
    } catch {
      setVideoError("No se pudo renovar el video. Revisa tu conexión e inténtalo de nuevo.");
    } finally {
      recoveringRef.current = false;
      setRecovering(false);
    }
  }

  function skip(seconds) {
    const video = videoRef.current;
    if (!video) return;
    const duration = Number(video.duration);
    const target = Number(video.currentTime || 0) + seconds;
    video.currentTime = Math.max(0, Number.isFinite(duration) && duration > 0
      ? Math.min(duration, target)
      : target);
  }

  function changeSpeed(event) {
    const rate = Number(event.target.value);
    setSpeed(rate);
    if (videoRef.current) videoRef.current.playbackRate = rate;
  }

  function toggleFullscreen() {
    const video = videoRef.current;
    if (!video) return;
    if (document.fullscreenElement && document.exitFullscreen) {
      void document.exitFullscreen();
    } else if (video.requestFullscreen) {
      void video.requestFullscreen();
    } else if (video.webkitEnterFullscreen) {
      video.webkitEnterFullscreen();
    }
  }

  return (
    <>
      <video
        ref={videoRef}
        controls
        playsInline
        preload="metadata"
        src={playbackUrl}
        aria-label={"Video: " + lesson.title}
        onLoadedMetadata={handleLoadedMetadata}
        onPlay={handlePlay}
        onTimeUpdate={handleTimeUpdate}
        onSeeking={handleSeeking}
        onSeeked={handleSeeked}
        onPause={handlePause}
        onEnded={handleEnded}
        onError={() => { void recoverVideo(true); }}
      >
        Tu navegador no puede reproducir este video.
      </video>
      <div className="training-video-toolbar" aria-label="Controles adicionales del video">
        <div className="training-video-toolbar-actions">
          <button type="button" onClick={() => skip(-10)} aria-label="Retroceder 10 segundos">−10 s</button>
          <button type="button" onClick={() => skip(10)} aria-label="Adelantar 10 segundos">+10 s</button>
          <label>
            Velocidad
            <select aria-label="Velocidad de reproducción" value={speed} onChange={changeSpeed}>
              {SPEEDS.map((rate) => <option key={rate} value={rate}>{rate}×</option>)}
            </select>
          </label>
        </div>
        <div className="training-video-toolbar-actions">
          {managedVideo && (
            <button type="button" onClick={() => { void recoverVideo(); }} disabled={recovering}>
              {recovering ? "Renovando…" : "Recargar video"}
            </button>
          )}
          <button type="button" onClick={toggleFullscreen}>Pantalla completa</button>
        </div>
      </div>
      {videoError && (
        <p role="alert" className="training-video-error">
          {videoError} {managedVideo && (
            <button type="button" onClick={() => { void recoverVideo(); }} disabled={recovering}>
              Reintentar
            </button>
          )}
        </p>
      )}
      <div className="training-video-watch-progress" aria-live="polite">
        <div>
          <strong>{Math.round(watchedPercent)}% reproducido</strong>
          <span>
            {lesson.completed
              ? "Video completado"
              : "Se completa automáticamente al reproducir al menos el " + threshold + "%."}
          </span>
        </div>
        <ProgressBar value={watchedPercent} />
      </div>
    </>
  );
}
