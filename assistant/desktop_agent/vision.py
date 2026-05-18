"""
Screen Vision Module

Provides screen vision capabilities:
- Screenshot capture
- OCR (Windows OCR API)
- Image template matching
- Element detection
"""

import logging
import os
import time
from pathlib import Path

# Optional imports
logger = logging.getLogger(__name__)

cv2 = None
numpy = None

try:
    import cv2
except ImportError:
    logger.warning("opencv-python not installed - image matching disabled")

try:
    import numpy as np

    numpy = np
except ImportError:
    logger.warning("numpy not installed - image processing disabled")

# Try to import PIL
try:
    from PIL import Image, ImageGrab

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow not available - screenshots disabled")

# Try to import pyautogui for screenshots
try:
    import pyautogui

    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

# Check for Windows OCR
WINDOWS_OCR_AVAILABLE = False
OCR_ENGINE = None

try:
    from azure.ai.vision import VisionSessionOptions, VisionSource

    WINDOWS_OCR_AVAILABLE = True
    OCR_ENGINE = "azure"
    logger.info("Windows OCR (Azure) available")
except ImportError:
    try:
        import pytesseract

        WINDOWS_OCR_AVAILABLE = True
        OCR_ENGINE = "tesseract"
        logger.info("Tesseract OCR available")
    except ImportError:
        logger.warning(
            "No OCR engine available - install pytesseract or azure-ai-vision-screenanalysis"
        )


class ScreenVision:
    """
    Screen vision capabilities.

    Provides screenshot capture, OCR, and image matching.
    """

    def __init__(
        self,
        ocr_enabled: bool = True,
        confidence: float = 0.8,
    ):
        """
        Initialize ScreenVision.

        Args:
            ocr_enabled: Enable OCR capability
            confidence: Default confidence threshold for image matching
        """
        self._ocr_enabled = ocr_enabled and WINDOWS_OCR_AVAILABLE
        self._confidence = confidence
        self._ocr_engine = OCR_ENGINE

        logger.info(
            f"ScreenVision initialized (OCR={self._ocr_enabled}, engine={self._ocr_engine})"
        )

    @property
    def ocr_enabled(self) -> bool:
        return self._ocr_enabled

    def take_screenshot(
        self,
        region: tuple[int, int, int, int] | None = None,
        save_path: str | None = None,
    ) -> np.ndarray | None:
        """
        Take a screenshot.

        Args:
            region: (x, y, width, height) region to capture (None = full screen)
            save_path: Path to save image (None = don't save)

        Returns:
            Screenshot as numpy array (BGR) or None
        """
        try:
            if PYAUTOGUI_AVAILABLE:
                if region:
                    screenshot = pyautogui.screenshot(region=region)
                else:
                    screenshot = pyautogui.screenshot()
            elif PIL_AVAILABLE:
                if region:
                    screenshot = ImageGrab.grab(bbox=region)
                else:
                    screenshot = ImageGrab.grab()
            else:
                logger.error("No screenshot capability available")
                return None

            # Convert to RGB for consistency
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            if save_path:
                cv2.imwrite(save_path, img)
                logger.info(f"Screenshot saved to {save_path}")

            return img

        except Exception as e:
            logger.error(f"take_screenshot failed: {e}")
            return None

    def save_screenshot(
        self,
        path: str = "screenshots/screen.png",
        region: tuple[int, int, int, int] | None = None,
    ) -> bool:
        """
        Take and save a screenshot.

        Args:
            path: Path to save screenshot
            region: (x, y, width, height) region

        Returns:
            bool: True if successful
        """
        try:
            # Ensure directory exists
            Path(path).parent.mkdir(parents=True, exist_ok=True)

            if PYAUTOGUI_AVAILABLE:
                if region:
                    img = pyautogui.screenshot(region=region)
                else:
                    img = pyautogui.screenshot()
            elif PIL_AVAILABLE:
                if region:
                    img = ImageGrab.grab(bbox=region)
                else:
                    img = ImageGrab.grab()
            else:
                return False

            img.save(path)
            return True

        except Exception as e:
            logger.error(f"save_screenshot failed: {e}")
            return False

    def capture_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> np.ndarray | None:
        """
        Capture a screen region.

        Args:
            x: X coordinate
            y: Y coordinate
            width: Region width
            height: Region height

        Returns:
            Image as numpy array or None
        """
        return self.take_screenshot(region=(x, y, width, height))

    def find_image(
        self,
        template_path: str,
        image: np.ndarray | None = None,
        confidence: float = 0.8,
    ) -> tuple[int, int] | None:
        """
        Find an image template on screen.

        Args:
            template_path: Path to template image
            image: Image to search in (None = take screenshot)
            confidence: Match confidence threshold

        Returns:
            (x, y) center position of match or None
        """
        try:
            if not os.path.exists(template_path):
                logger.error(f"Template not found: {template_path}")
                return None

            # Load template
            template = cv2.imread(template_path)
            if template is None:
                logger.error(f"Failed to load template: {template_path}")
                return None

            # Get image to search
            if image is None:
                image = self.take_screenshot()
                if image is None:
                    return None

            # Convert to grayscale
            gray_img = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

            # Template matching
            result = cv2.matchTemplate(gray_img, gray_template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= confidence:
                h, w = gray_template.shape
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                logger.info(
                    f"Found template at ({center_x}, {center_y}) confidence={max_val:.2f}"
                )
                return (center_x, center_y)

            logger.info(f"Template not found (best match: {max_val:.2f})")
            return None

        except Exception as e:
            logger.error(f"find_image failed: {e}")
            return None

    def find_all_images(
        self,
        template_path: str,
        image: np.ndarray | None = None,
        confidence: float = 0.8,
        max_results: int = 10,
    ) -> list[tuple[int, int]]:
        """
        Find all instances of an image template.

        Args:
            template_path: Path to template image
            image: Image to search in
            confidence: Match confidence threshold
            max_results: Maximum number of results

        Returns:
            List of (x, y) positions
        """
        try:
            if not os.path.exists(template_path):
                return []

            template = cv2.imread(template_path)
            if template is None:
                return []

            if image is None:
                image = self.take_screenshot()
                if image is None:
                    return []

            gray_img = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

            result = cv2.matchTemplate(gray_img, gray_template, cv2.TM_CCOEFF_NORMED)

            locations = np.where(result >= confidence)

            positions = []
            h, w = gray_template.shape

            for pt in zip(*locations[::-1], strict=False):
                if len(positions) >= max_results:
                    break
                positions.append((pt[0] + w // 2, pt[1] + h // 2))

            return positions

        except Exception as e:
            logger.error(f"find_all_images failed: {e}")
            return []

    def ocr_screen(
        self,
        region: tuple[int, int, int, int] | None = None,
    ) -> str:
        """
        Read text from screen using OCR.

        Args:
            region: (x, y, width, height) region to read (None = full screen)

        Returns:
            OCR text or empty string
        """
        if not self._ocr_enabled:
            logger.warning("OCR not available")
            return ""

        try:
            img = self.take_screenshot(region=region)
            if img is None:
                return ""

            # Process based on engine
            if self._ocr_engine == "azure":
                return self._ocr_azure(img)
            elif self._ocr_engine == "tesseract":
                return self._ocr_tesseract(img)

            return ""

        except Exception as e:
            logger.error(f"ocr_screen failed: {e}")
            return ""

    def _ocr_azure(self, image: np.ndarray) -> str:
        """OCR using Azure Vision API."""
        try:
            from azure.ai.vision import VisionSource

            # Save temp image
            temp_path = "screenshots/temp_ocr.png"
            cv2.imwrite(temp_path, image)

            # Analyze
            VisionSource(url=f"file:///{os.path.abspath(temp_path)}")

            # Note: This requires Azure subscription
            # Use tesseract as fallback for local-only
            return self._ocr_tesseract(image)

        except Exception as e:
            logger.error(f"Azure OCR failed: {e}")
            return self._ocr_tesseract(image)

    def _ocr_tesseract(self, image: np.ndarray) -> str:
        """OCR using Tesseract."""
        try:
            import pytesseract

            # Convert to RGB for tesseract
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            # OCR
            text = pytesseract.image_to_string(rgb)

            return text.strip()

        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            return ""

    def ocr_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> str:
        """
        OCR a specific region.

        Args:
            x: X coordinate
            y: Y coordinate
            width: Region width
            height: Region height

        Returns:
            OCR text
        """
        return self.ocr_screen(region=(x, y, width, height))

    def get_pixel_color(
        self,
        x: int,
        y: int,
    ) -> tuple[int, int, int] | None:
        """
        Get pixel color at position.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            (B, G, R) color or None
        """
        try:
            img = self.take_screenshot()
            if img is None:
                return None

            # Bounds check
            h, w = img.shape[:2]
            if x < 0 or x >= w or y < 0 or y >= h:
                return None

            return tuple(img[y, x])

        except Exception as e:
            logger.error(f"get_pixel_color failed: {e}")
            return None

    def wait_for_image(
        self,
        template_path: str,
        timeout: float = 10.0,
        confidence: float = 0.8,
    ) -> tuple[int, int] | None:
        """
        Wait for an image to appear on screen.

        Args:
            template_path: Path to template image
            timeout: Maximum wait time in seconds
            confidence: Match confidence

        Returns:
            (x, y) position when found, or None on timeout
        """
        start = time.time()

        while time.time() - start < timeout:
            pos = self.find_image(template_path, confidence=confidence)
            if pos:
                return pos
            time.sleep(0.5)

        return None


def get_screen_vision(ocr_enabled: bool = True) -> ScreenVision:
    """Factory function to create ScreenVision."""
    return ScreenVision(ocr_enabled=ocr_enabled)
