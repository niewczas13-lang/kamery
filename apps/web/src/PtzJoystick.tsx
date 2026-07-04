import { commandLabel, defaultPtzDurationMs, ptzCommandAllowed, ptzControlsForCamera, ptzStatusMessage, type PtzUiState } from "./ptz";
import type { Camera, PtzCommand } from "./types";

type PtzJoystickProps = {
  camera: Camera;
  state: PtzUiState;
  speed: number;
  durationMs?: number;
  movementUnlocked: boolean;
  onCommand: (command: PtzCommand, durationMs: number, speed: number) => void;
};

export function PtzJoystick({ camera, state, speed, durationMs = defaultPtzDurationMs(), movementUnlocked, onCommand }: PtzJoystickProps) {
  const controls = ptzControlsForCamera(camera);
  if (!camera.has_ptz) {
    return (
      <section className="ptz-console disabled">
        <div>
          <h4>Sterowanie kamerą fizyczną</h4>
          <p>PTZ niedostępne dla tej kamery.</p>
        </div>
      </section>
    );
  }

  const isUnstable = camera.reliability_status === "unstable";
  const control = (command: PtzCommand) => controls.find((item) => item.command === command);

  return (
    <section className="ptz-console">
      <div className="ptz-console-head">
        <div>
          <h4>Sterowanie kamerą fizyczną</h4>
          <p>Tryb bezpiecznego ruchu: {durationMs} ms, prędkość {speedLabel(speed)}.</p>
        </div>
        <span className="badge info">Bezpieczny ruch</span>
      </div>
      {isUnstable ? <p className="warning-text">Kamera niestabilna. Ruchy testuj krótkimi kliknięciami.</p> : null}
      <div className="ptz-radial" aria-label="Joystick PTZ">
        <span />
        <PtzButton control={control("up")} disabled={!ptzCommandAllowed("up", movementUnlocked)} onClick={() => onCommand("up", durationMs, speed)} />
        <span />
        <PtzButton control={control("left")} disabled={!ptzCommandAllowed("left", movementUnlocked)} onClick={() => onCommand("left", durationMs, speed)} />
        <PtzButton control={control("stop")} variant="stop" onClick={() => onCommand("stop", durationMs, speed)} />
        <PtzButton control={control("right")} disabled={!ptzCommandAllowed("right", movementUnlocked)} onClick={() => onCommand("right", durationMs, speed)} />
        <PtzButton control={control("zoom_out")} disabled={!ptzCommandAllowed("zoom_out", movementUnlocked)} onClick={() => onCommand("zoom_out", durationMs, speed)} />
        <PtzButton control={control("down")} disabled={!ptzCommandAllowed("down", movementUnlocked)} onClick={() => onCommand("down", durationMs, speed)} />
        <PtzButton control={control("zoom_in")} disabled={!ptzCommandAllowed("zoom_in", movementUnlocked)} onClick={() => onCommand("zoom_in", durationMs, speed)} />
      </div>
      <p className={`ptz-state ${state.state}`}>{ptzStatusMessage(state) || `Gotowe: ${commandLabel("stop")}`}</p>
    </section>
  );
}

function PtzButton({
  control,
  variant,
  disabled = false,
  onClick
}: {
  control: { command: PtzCommand; label: string } | undefined;
  variant?: "stop";
  disabled?: boolean;
  onClick: () => void;
}) {
  if (!control) {
    return <span />;
  }
  return (
    <button
      className={variant === "stop" ? "ptz-button stop" : "ptz-button"}
      type="button"
      aria-label={`PTZ ${control.label}`}
      disabled={disabled}
      title={disabled ? "PTZ zablokowane. Odblokuj ruch w panelu focus mode." : undefined}
      onClick={onClick}
    >
      {variant === "stop" ? "STOP" : control.label}
    </button>
  );
}

function speedLabel(speed: number): string {
  if (speed <= 0.2) {
    return "wolna";
  }
  if (speed >= 0.6) {
    return "szybka";
  }
  return "średnia";
}
