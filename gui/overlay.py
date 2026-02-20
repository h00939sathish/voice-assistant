"""
Floating Overlay - Siri-like Glowing Orb
"""

import tkinter as tk
import time
import math


class AssistantOverlay:
    """
    Transparent floating window with animated glowing orb.
    """

    def __init__(self, root):
        self.root = root

        # Window setup
        self.root.overrideredirect(True)  # Remove title bar
        self.root.wm_attributes("-topmost", True)  # Always on top
        self.root.wm_attributes("-transparentcolor", "black")  # Transparency key

        # Orb size
        self.orb_size = 100
        self.width = self.orb_size + 40
        self.height = self.orb_size + 40

        # Position: Bottom Right
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = screen_width - self.width - 40
        y = screen_height - self.height - 100
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

        # Canvas for drawing
        self.canvas = tk.Canvas(
            root, width=self.width, height=self.height, bg="black", highlightthickness=0
        )
        self.canvas.pack()

        # State
        self.state = "IDLE"
        self._animation_phase = 0.0

        # Colors for states
        self.colors = {
            "IDLE": "#555555",
            "AMBIENT": "#9C27B0",  # Purple
            "WAKE": "#4A90D9",
            "LISTENING": "#4A90D9",  # Blue
            "PROCESSING": "#FFC107",  # Amber
            "SPEAKING": "#00C8B4",  # Cyan/Teal
        }

        # Draw initial orb
        self.center = self.width // 2
        self.base_radius = self.orb_size // 2 - 10

        # Glow layers (outer to inner)
        self.glow_outer = self.canvas.create_oval(0, 0, 0, 0, fill="", outline="")
        self.glow_mid = self.canvas.create_oval(0, 0, 0, 0, fill="", outline="")
        self.orb = self.canvas.create_oval(
            0, 0, 0, 0, fill="#4A90D9", outline="white", width=2
        )

        # Animation
        self.animating = True
        self._animate()

        # Initial: Hidden
        self.hide()

    def set_state(self, state, text=None):
        """Update visual state"""
        self.state = state
        color = self.colors.get(state, "#555555")
        self.canvas.itemconfig(self.orb, fill=color)

        if state == "IDLE":
            self.hide()
        else:
            self.show()

    def _animate(self):
        """Smooth pulse animation"""
        if self.state not in ("IDLE",):
            self._animation_phase += 0.12
            if self._animation_phase > 2 * math.pi:
                self._animation_phase = 0

            pulse = (math.sin(self._animation_phase) + 1) / 2  # 0 to 1
            pulse_amount = 8 * pulse

            color = self.colors.get(self.state, "#555555")

            # Update orb size
            r = self.base_radius + pulse_amount
            cx, cy = self.center, self.center
            self.canvas.coords(self.orb, cx - r, cy - r, cx + r, cy + r)

            # Outer glow (larger, faded)
            glow_r = r + 15
            alpha_hex = format(int(60 * (0.3 + 0.7 * pulse)), "02x")
            # Tkinter doesn't support alpha, so we just show/hide
            self.canvas.coords(
                self.glow_outer, cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r
            )
            self.canvas.itemconfig(self.glow_outer, outline=color, width=3)

            # Mid glow
            mid_r = r + 8
            self.canvas.coords(
                self.glow_mid, cx - mid_r, cy - mid_r, cx + mid_r, cy + mid_r
            )
            self.canvas.itemconfig(self.glow_mid, outline=color, width=2)

        self.root.after(30, self._animate)

    def show(self):
        self.root.deiconify()
        self.root.lift()

    def hide(self):
        self.root.withdraw()


# For testing independently
if __name__ == "__main__":
    import threading

    root = tk.Tk()
    app = AssistantOverlay(root)

    # Test state cycle
    def cycle_states():
        states = ["LISTENING", "PROCESSING", "SPEAKING", "IDLE", "LISTENING"]
        for i, state in enumerate(states):
            time.sleep(2)
            root.after(0, lambda s=state: app.set_state(s))

    threading.Thread(target=cycle_states, daemon=True).start()

    app.set_state("LISTENING")
    root.mainloop()
