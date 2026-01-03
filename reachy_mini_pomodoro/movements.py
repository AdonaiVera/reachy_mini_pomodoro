"""Robot movements and expressions for the Pomodoro app."""

import math
import random
import time
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

import numpy as np
from scipy.spatial.transform import Rotation as R


class MovementType(Enum):
    """Types of movements the robot can perform."""
    IDLE = "idle"
    BREATHING = "breathing"
    TALKING = "talking"
    LISTENING = "listening"
    FOCUS_START = "focus_start"
    FOCUS_REMINDER = "focus_reminder"
    FOCUS_COMPLETE = "focus_complete"
    BREAK_START = "break_start"
    BREAK_ACTIVITY = "break_activity"
    TASK_COMPLETE = "task_complete"
    CELEBRATION = "celebration"
    NOD_YES = "nod_yes"
    NOD_NO = "nod_no"
    LOOK_AROUND = "look_around"
    STRETCH_DEMO = "stretch_demo"
    BREATHING_DEMO = "breathing_demo"


@dataclass
class MovementState:
    """Current state of a movement animation."""
    movement_type: MovementType
    start_time: float
    duration: float
    loop: bool = False
    data: Optional[dict] = None

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def progress(self) -> float:
        if self.loop:
            return (self.elapsed % self.duration) / self.duration
        return min(1.0, self.elapsed / self.duration)

    @property
    def is_complete(self) -> bool:
        if self.loop:
            return False
        return self.elapsed >= self.duration


class MovementManager:
    """Manages robot movements and animations.

    Supports two layers of movement:
    1. Primary movements (focus, celebration, etc.) - managed by start_movement/queue_movement
    2. Speech offsets - audio-driven head wobble layered on top of primary movements
    """

    def __init__(self) -> None:
        self.current_movement: Optional[MovementState] = None
        self.queued_movements: list[MovementState] = []
        self._base_time = time.time()

        self._speech_offsets: Tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        self._speech_offsets_lock = threading.Lock()
        self._is_listening = False

    def start_movement(self, movement_type: MovementType, duration: float = 2.0,
                       loop: bool = False, data: Optional[dict] = None) -> None:
        """Start a new movement, replacing any current movement."""
        self.current_movement = MovementState(
            movement_type=movement_type,
            start_time=time.time(),
            duration=duration,
            loop=loop,
            data=data,
        )

    def queue_movement(self, movement_type: MovementType, duration: float = 2.0,
                       loop: bool = False, data: Optional[dict] = None) -> None:
        """Queue a movement to play after the current one."""
        self.queued_movements.append(MovementState(
            movement_type=movement_type,
            start_time=0,  # Will be set when it starts
            duration=duration,
            loop=loop,
            data=data,
        ))

    def stop_movement(self) -> None:
        """Stop the current movement and return to idle."""
        self.current_movement = None
        self.queued_movements.clear()

    def set_speech_offsets(self, offsets: Tuple[float, float, float, float, float, float]) -> None:
        """Set speech-driven head movement offsets.

        These offsets are layered on top of primary movements for realistic talking animation.

        Args:
            offsets: Tuple of (x, y, z, roll, pitch, yaw) in meters/radians.
        """
        with self._speech_offsets_lock:
            self._speech_offsets = offsets

    def clear_speech_offsets(self) -> None:
        """Reset speech offsets to zero."""
        with self._speech_offsets_lock:
            self._speech_offsets = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def set_listening(self, listening: bool) -> None:
        """Set whether the robot is listening (affects subtle animations)."""
        self._is_listening = listening

    def update(self) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Update and return the current pose.

        Returns:
            Tuple of (head_pose 4x4, antennas [right, left], body_yaw)
        """
        if self.current_movement and self.current_movement.is_complete:
            if self.queued_movements:
                next_move = self.queued_movements.pop(0)
                next_move.start_time = time.time()
                self.current_movement = next_move
            else:
                self.current_movement = None

        if self.current_movement is None:
            pose, antennas, body_yaw = self._idle_pose()
        else:
            movement_type = self.current_movement.movement_type
            progress = self.current_movement.progress
            elapsed = self.current_movement.elapsed

            if movement_type == MovementType.IDLE:
                pose, antennas, body_yaw = self._idle_pose()
            elif movement_type == MovementType.BREATHING:
                pose, antennas, body_yaw = self._breathing_pose(elapsed)
            elif movement_type == MovementType.TALKING:
                pose, antennas, body_yaw = self._talking_pose(elapsed)
            elif movement_type == MovementType.LISTENING:
                pose, antennas, body_yaw = self._listening_pose(elapsed)
            elif movement_type == MovementType.FOCUS_START:
                pose, antennas, body_yaw = self._focus_start_pose(progress)
            elif movement_type == MovementType.FOCUS_REMINDER:
                pose, antennas, body_yaw = self._focus_reminder_pose(progress)
            elif movement_type == MovementType.FOCUS_COMPLETE:
                pose, antennas, body_yaw = self._focus_complete_pose(progress)
            elif movement_type == MovementType.BREAK_START:
                pose, antennas, body_yaw = self._break_start_pose(progress)
            elif movement_type == MovementType.CELEBRATION:
                pose, antennas, body_yaw = self._celebration_pose(elapsed)
            elif movement_type == MovementType.TASK_COMPLETE:
                pose, antennas, body_yaw = self._task_complete_pose(elapsed)
            elif movement_type == MovementType.NOD_YES:
                pose, antennas, body_yaw = self._nod_yes_pose(progress)
            elif movement_type == MovementType.NOD_NO:
                pose, antennas, body_yaw = self._nod_no_pose(progress)
            elif movement_type == MovementType.LOOK_AROUND:
                pose, antennas, body_yaw = self._look_around_pose(elapsed)
            elif movement_type == MovementType.STRETCH_DEMO:
                pose, antennas, body_yaw = self._stretch_demo_pose(progress)
            elif movement_type == MovementType.BREATHING_DEMO:
                pose, antennas, body_yaw = self._breathing_demo_pose(elapsed)
            else:
                pose, antennas, body_yaw = self._idle_pose()

        pose = self._apply_speech_offsets(pose)

        return pose, antennas, body_yaw

    def _apply_speech_offsets(self, base_pose: np.ndarray) -> np.ndarray:
        """Apply speech-driven offsets to the base pose.

        Args:
            base_pose: The 4x4 pose matrix from the primary movement.

        Returns:
            Modified 4x4 pose matrix with speech offsets applied.
        """
        with self._speech_offsets_lock:
            x, y, z, roll, pitch, yaw = self._speech_offsets

        if x == 0 and y == 0 and z == 0 and roll == 0 and pitch == 0 and yaw == 0:
            return base_pose

        offset_pose = np.eye(4)
        offset_pose[:3, :3] = R.from_euler(
            "xyz", [math.degrees(roll), math.degrees(pitch), math.degrees(yaw)], degrees=True
        ).as_matrix()
        offset_pose[:3, 3] = [x, y, z]

        return base_pose @ offset_pose

    def _create_pose(self, roll: float = 0, pitch: float = 0, yaw: float = 0,
                     x: float = 0, y: float = 0, z: float = 0) -> np.ndarray:
        """Create a 4x4 pose matrix from euler angles (degrees) and position (mm)."""
        pose = np.eye(4)
        pose[:3, :3] = R.from_euler("xyz", [roll, pitch, yaw], degrees=True).as_matrix()
        pose[:3, 3] = [x / 1000, y / 1000, z / 1000]  # Convert mm to m
        return pose

    def _idle_pose(self) -> Tuple[np.ndarray, np.ndarray, float]:
        """Subtle idle breathing animation."""
        t = time.time() - self._base_time
        pitch = 2 * math.sin(2 * math.pi * 0.15 * t)
        z = 3 * math.sin(2 * math.pi * 0.15 * t)

        antenna_offset = 0.05 * math.sin(2 * math.pi * 0.2 * t)

        pose = self._create_pose(pitch=pitch, z=z)
        antennas = np.array([antenna_offset, -antenna_offset])
        return pose, antennas, 0.0

    def _breathing_pose(self, elapsed: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Calm breathing animation for focus time."""
        pitch = 5 * math.sin(2 * math.pi * 0.1 * elapsed)
        z = 8 * math.sin(2 * math.pi * 0.1 * elapsed)

        antenna_base = 0.3  # Raised position
        antenna_variation = 0.1 * math.sin(2 * math.pi * 0.1 * elapsed)

        pose = self._create_pose(pitch=pitch, z=z)
        antennas = np.array([antenna_base + antenna_variation, antenna_base - antenna_variation])
        return pose, antennas, 0.0

    def _talking_pose(self, elapsed: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Subtle talking animation - small nods and tilts like natural speech."""
        nod_fast = 3 * math.sin(2 * math.pi * 2.5 * elapsed)  # Fast subtle nods
        nod_slow = 2 * math.sin(2 * math.pi * 0.8 * elapsed)  # Slower emphasis nods
        pitch = nod_fast + nod_slow

        roll = 2 * math.sin(2 * math.pi * 0.6 * elapsed + 0.5)

        yaw = 3 * math.sin(2 * math.pi * 0.4 * elapsed)

        antenna_base = 0.25
        antenna_wiggle = 0.1 * math.sin(2 * math.pi * 1.5 * elapsed)

        pose = self._create_pose(roll=roll, pitch=pitch, yaw=yaw)
        antennas = np.array([antenna_base + antenna_wiggle, antenna_base - antenna_wiggle])
        return pose, antennas, 0.0

    def _listening_pose(self, elapsed: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Attentive listening pose - focused attention with expressive antennas."""
        pitch = -5
        roll = 2 * math.sin(2 * math.pi * 0.4 * elapsed)
        yaw = 3 * math.sin(2 * math.pi * 0.25 * elapsed)

        antenna_base = 0.45
        antenna_wave = 0.15 * math.sin(2 * math.pi * 0.6 * elapsed)
        antenna_flutter = 0.05 * math.sin(2 * math.pi * 1.5 * elapsed)

        right_antenna = antenna_base + antenna_wave + antenna_flutter
        left_antenna = antenna_base + 0.12 * math.sin(2 * math.pi * 0.6 * elapsed + 0.3) + antenna_flutter

        pose = self._create_pose(roll=roll, pitch=pitch, yaw=yaw)
        antennas = np.array([right_antenna, left_antenna])
        return pose, antennas, 0.0

    def _focus_start_pose(self, progress: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Animation when starting a focus session."""
        if progress < 0.3:
            p = progress / 0.3
            pitch = -15 * math.sin(math.pi * p)
            roll = 10 * math.sin(math.pi * p)
        elif progress < 0.6:
            p = (progress - 0.3) / 0.3
            pitch = -15 * (1 - p) * math.sin(math.pi * 0.5)
            roll = 10 * (1 - p)
        else:
            pitch = 0
            roll = 0

        antenna_up = 0.5 * min(1.0, progress * 2)

        pose = self._create_pose(roll=roll, pitch=pitch)
        antennas = np.array([antenna_up, antenna_up])
        return pose, antennas, 0.0

    def _focus_reminder_pose(self, progress: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Gentle reminder during focus session."""
        if progress < 0.5:
            p = progress / 0.5
            roll = 8 * math.sin(math.pi * p)
            yaw = 5 * math.sin(math.pi * p)
        else:
            p = (progress - 0.5) / 0.5
            roll = 8 * (1 - p)
            yaw = 5 * (1 - p)

        pose = self._create_pose(roll=roll, yaw=yaw)
        antennas = np.array([0.2, 0.2])
        return pose, antennas, 0.0

    def _focus_complete_pose(self, progress: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Celebration when focus session completes."""
        bounce = math.sin(math.pi * progress * 2) * (1 - progress)  # Slowed from 4
        z = 15 * bounce
        pitch = -10 * bounce

        antenna_wave = 0.5 * math.sin(math.pi * progress * 3)  # Slowed from 6

        pose = self._create_pose(pitch=pitch, z=z)
        antennas = np.array([0.3 + antenna_wave, 0.3 - antenna_wave])
        return pose, antennas, 0.0

    def _break_start_pose(self, progress: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Relaxed pose when break starts."""
        if progress < 0.4:
            p = progress / 0.4
            pitch = -10 * p  
            z = 10 * p
        else:
            p = (progress - 0.4) / 0.6
            pitch = -10 + 15 * p  
            z = 10 - 5 * p

        antenna_pos = 0.4 * (1 - progress)

        pose = self._create_pose(pitch=pitch, z=z)
        antennas = np.array([antenna_pos, antenna_pos])
        return pose, antennas, 0.0

    def _celebration_pose(self, elapsed: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Victory dance for completing tasks."""
        bounce_freq = 1.0
        sway_freq = 0.5

        z = 15 * abs(math.sin(2 * math.pi * bounce_freq * elapsed))
        yaw = 20 * math.sin(2 * math.pi * sway_freq * elapsed)
        roll = 15 * math.sin(2 * math.pi * sway_freq * elapsed + math.pi / 4)

        antenna_wave = 0.6 * math.sin(2 * math.pi * 0.8 * elapsed)  # Slowed from 4.0

        pose = self._create_pose(roll=roll, yaw=yaw, z=z)
        antennas = np.array([antenna_wave, -antenna_wave])
        return pose, antennas, 0.0

    def _task_complete_pose(self, elapsed: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Happy animation when a task is completed."""
        if elapsed < 1.0:
            z = 20 * math.sin(math.pi * elapsed)
            pitch = -15 * math.sin(math.pi * elapsed)
            antenna_up = 0.7
        else:
            p = min(1.0, elapsed - 1.0)
            z = 0
            pitch = 0
            antenna_up = 0.7 * (1 - p)

        pose = self._create_pose(pitch=pitch, z=z)
        antennas = np.array([antenna_up, antenna_up])
        return pose, antennas, 0.0

    def _nod_yes_pose(self, progress: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Nodding yes animation."""
        nod_cycle = progress * 2
        pitch = -12 * math.sin(math.pi * nod_cycle * 2)

        pose = self._create_pose(pitch=pitch)
        antennas = np.array([0.2, 0.2])
        return pose, antennas, 0.0

    def _nod_no_pose(self, progress: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Shaking head no animation."""
        shake_cycle = progress * 2
        yaw = 15 * math.sin(math.pi * shake_cycle * 2)

        pose = self._create_pose(yaw=yaw)
        antennas = np.array([-0.2, -0.2])
        return pose, antennas, 0.0

    def _look_around_pose(self, elapsed: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Looking around curiously."""
        yaw = 30 * math.sin(2 * math.pi * 0.3 * elapsed)
        pitch = 10 * math.sin(2 * math.pi * 0.2 * elapsed + 0.5)

        antenna_offset = 0.3 * math.sin(2 * math.pi * 0.4 * elapsed)

        pose = self._create_pose(yaw=yaw, pitch=pitch)
        antennas = np.array([0.3 + antenna_offset, 0.3 - antenna_offset])
        return pose, antennas, 0.0

    def _stretch_demo_pose(self, progress: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Demonstrate stretching (neck stretches)."""
        cycle = progress * 4
        if cycle < 1:
            p = cycle
            yaw = 25 * math.sin(math.pi * p)
        elif cycle < 2:
            p = cycle - 1
            yaw = -25 * math.sin(math.pi * p)
        elif cycle < 3:
            p = cycle - 2
            yaw = 0
            pitch = -20 * math.sin(math.pi * p)
        else:
            p = cycle - 3
            yaw = 0
            pitch = 15 * math.sin(math.pi * p)

        if cycle < 2:
            pitch = 0

        pose = self._create_pose(yaw=yaw, pitch=pitch)
        antennas = np.array([0.2, 0.2])
        return pose, antennas, 0.0

    def _breathing_demo_pose(self, elapsed: float) -> Tuple[np.ndarray, np.ndarray, float]:
        """Demonstrate deep breathing exercise."""
        cycle_duration = 12.0
        cycle_pos = (elapsed % cycle_duration) / cycle_duration

        if cycle_pos < 0.33:
            p = cycle_pos / 0.33
            z = 20 * p
            pitch = -10 * p
        elif cycle_pos < 0.66:
            z = 20
            pitch = -10
        else:
            p = (cycle_pos - 0.66) / 0.34
            z = 20 * (1 - p)
            pitch = -10 * (1 - p)

        antenna_pos = 0.4 * (z / 20)

        pose = self._create_pose(pitch=pitch, z=z)
        antennas = np.array([antenna_pos, antenna_pos])
        return pose, antennas, 0.0

    def get_current_movement_type(self) -> Optional[MovementType]:
        """Get the current movement type."""
        if self.current_movement:
            return self.current_movement.movement_type
        return None
