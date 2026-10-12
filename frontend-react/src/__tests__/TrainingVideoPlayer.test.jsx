// eslint-disable-next-line no-unused-vars
import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import TrainingVideoPlayer from "../features/training/TrainingVideoPlayer";

function makeLesson(patch = {}) {
  return {
    id: "lesson-1",
    title: "Bienvenida ASIATI",
    content_type: "VIDEO",
    video_url: "https://media.example.com/onboarding.mp4?sig=original",
    video_source: "managed",
    duration_seconds: 120,
    completed: false,
    video_progress: {
      watched_percent: 25,
      last_position_seconds: 30,
      completion_threshold_percent: 80,
    },
    ...patch,
  };
}

function readyVideo(video, duration = 120) {
  Object.defineProperty(video, "duration", { configurable: true, value: duration });
  fireEvent.loadedMetadata(video);
  return video;
}

function simulatePlaying(video) {
  Object.defineProperty(video, "paused", { configurable: true, value: false });
  fireEvent.play(video);
}

describe("TrainingVideoPlayer", () => {
  it("holds the playback source stable through progress updates and replays its saved position", () => {
    const save = vi.fn().mockResolvedValue({});
    const lesson = makeLesson();
    const { rerender } = render(<TrainingVideoPlayer lesson={lesson} onVideoProgress={save} />);
    const video = readyVideo(screen.getByLabelText("Video: Bienvenida ASIATI"));
    expect(video.currentTime).toBe(30);
    const refreshed = makeLesson({
      video_url: "https://media.example.com/onboarding.mp4?sig=refreshed",
      video_progress: { watched_percent: 40, last_position_seconds: 48, completion_threshold_percent: 80 },
    });
    rerender(<TrainingVideoPlayer lesson={refreshed} onVideoProgress={save} />);
    expect(screen.getByLabelText("Video: Bienvenida ASIATI")).toBe(video);
    expect(video).toHaveAttribute("src", lesson.video_url);
    expect(video.currentTime).toBe(30);
    expect(screen.getByText("40% reproducido")).toBeInTheDocument();
  });

  it("serializes playback segments when the user pauses while a save is running", async () => {
    let releaseFirst;
    const firstRequest = new Promise((resolve) => { releaseFirst = resolve; });
    const save = vi.fn()
      .mockImplementationOnce(() => firstRequest)
      .mockResolvedValue({});
    render(<TrainingVideoPlayer lesson={makeLesson()} onVideoProgress={save} />);
    const video = readyVideo(screen.getByLabelText("Video: Bienvenida ASIATI"));
    simulatePlaying(video);
    video.currentTime = 36;
    fireEvent.timeUpdate(video);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenNthCalledWith(1, expect.anything(), expect.objectContaining({
      played_from_seconds: 30,
      played_to_seconds: 36,
    }));

    video.currentTime = 43;
    fireEvent.pause(video);
    expect(save).toHaveBeenCalledTimes(1);
    await act(async () => { releaseFirst({}); });
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(save).toHaveBeenNthCalledWith(2, expect.anything(), expect.objectContaining({
      played_from_seconds: 36,
      played_to_seconds: 43,
      position_seconds: 43,
    }));
  });

  it("does not count manually skipped seconds as watched, even with seek buttons", async () => {
    const save = vi.fn().mockResolvedValue({});
    render(<TrainingVideoPlayer lesson={makeLesson()} onVideoProgress={save} />);
    const video = readyVideo(screen.getByLabelText("Video: Bienvenida ASIATI"));
    simulatePlaying(video);
    video.currentTime = 34;
    fireEvent.timeUpdate(video);
    fireEvent.seeking(video);
    video.currentTime = 94;
    fireEvent.seeked(video);
    video.currentTime = 100;
    fireEvent.timeUpdate(video);
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    const ranges = save.mock.calls.map(([, payload]) => [
      payload.played_from_seconds, payload.played_to_seconds,
    ]);
    expect(ranges).toEqual([[30, 34], [94, 100]]);
    fireEvent.click(screen.getByRole("button", { name: "Retroceder 10 segundos" }));
    expect(video.currentTime).toBe(90);
    fireEvent.click(screen.getByRole("button", { name: "Adelantar 10 segundos" }));
    expect(video.currentTime).toBe(100);
  });

  it("sends a keepalive segment when the tab is closed before the 5-second checkpoint", async () => {
    const save = vi.fn().mockResolvedValue({});
    const keepalive = vi.fn();
    const { unmount } = render(
      <TrainingVideoPlayer lesson={makeLesson({
        video_progress: { watched_percent: 0, last_position_seconds: 0 },
      })} onVideoProgress={save} onSaveOnExit={keepalive} />,
    );
    const video = readyVideo(screen.getByLabelText("Video: Bienvenida ASIATI"));
    simulatePlaying(video);
    video.currentTime = 3;
    fireEvent.timeUpdate(video);
    act(() => window.dispatchEvent(new Event("pagehide")));
    expect(keepalive).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
      played_from_seconds: 0,
      played_to_seconds: 3,
    }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    unmount();
  });

  it("splits long background stretches into segments accepted by the backend", async () => {
    const save = vi.fn().mockResolvedValue({});
    render(<TrainingVideoPlayer lesson={makeLesson({
      video_progress: { watched_percent: 0, last_position_seconds: 0 },
    })} onVideoProgress={save} />);
    const video = readyVideo(screen.getByLabelText("Video: Bienvenida ASIATI"));
    simulatePlaying(video);
    video.currentTime = 48;
    fireEvent.timeUpdate(video);
    await waitFor(() => expect(save).toHaveBeenCalledTimes(3));
    const segments = save.mock.calls.map(([, payload]) => [
      payload.played_from_seconds, payload.played_to_seconds,
    ]);
    expect(segments).toEqual([[0, 20], [20, 40], [40, 48]]);
  });

  it("refreshes an expired managed video URL and resumes from its last position", async () => {
    const save = vi.fn().mockResolvedValue({});
    const refresh = vi.fn().mockResolvedValue("https://media.example.com/onboarding.mp4?sig=renewed");
    render(
      <TrainingVideoPlayer lesson={makeLesson()} onVideoProgress={save} onRefreshVideoUrl={refresh} />,
    );
    const video = readyVideo(screen.getByLabelText("Video: Bienvenida ASIATI"));
    video.play = vi.fn().mockResolvedValue(undefined);
    simulatePlaying(video);
    video.currentTime = 44;

    fireEvent.error(video);
    await waitFor(() => expect(refresh).toHaveBeenCalledWith(expect.objectContaining({ id: "lesson-1" })));
    await waitFor(() => expect(video).toHaveAttribute("src", "https://media.example.com/onboarding.mp4?sig=renewed"));
    video.currentTime = 0;
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(44);
    expect(video.play).toHaveBeenCalled();
  });

  it("lets the employee control playback speed and enter fullscreen", () => {
    render(<TrainingVideoPlayer lesson={makeLesson()} onVideoProgress={vi.fn()} />);
    const video = readyVideo(screen.getByLabelText("Video: Bienvenida ASIATI"));
    fireEvent.change(screen.getByRole("combobox", { name: "Velocidad de reproducción" }), {
      target: { value: "1.5" },
    });
    expect(video.playbackRate).toBe(1.5);
    const fullscreen = vi.fn().mockResolvedValue(undefined);
    video.requestFullscreen = fullscreen;
    fireEvent.click(screen.getByRole("button", { name: "Pantalla completa" }));
    expect(fullscreen).toHaveBeenCalledOnce();
  });

  it("offers an explicit recovery option after an AWS error", async () => {
    const refresh = vi.fn().mockRejectedValue(new Error("Expired"));
    render(<TrainingVideoPlayer
      lesson={makeLesson()} onVideoProgress={vi.fn().mockResolvedValue({})}
      onRefreshVideoUrl={refresh}
    />);
    fireEvent.error(screen.getByLabelText("Video: Bienvenida ASIATI"));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo renovar el video");
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(2));
  });
});
