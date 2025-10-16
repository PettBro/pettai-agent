# 🎨 Image Assets

This folder should contain your image assets for the Pett Agent frontend.

## Required Images

Add the following images to enable all visual features:

### Backgrounds

- `background-0.jpg` - Splash screen background
- `background-1.jpg` - Login page background
- `background-3.jpg` - App content background (optional)
- `background-desktop.jpg` - Desktop outer background (optional)

### Decorative Elements

- `floating-1.png` - Rocket/floating element (bottom-left on login, bottom on splash)
- `floating-2.png` - Stars/floating element (top-right on login)

### Branding

- `logo.svg` - Main logo (displayed on splash screen)

## How to Add Images

1. **Place your images** in this directory:

   ```
   /public/assets/images/
   ```

2. **Uncomment the image tags** in the components:

   **SplashScreen.jsx:**

   ```jsx
   // Remove the {/* */} comments around:
   <img src="/assets/images/background-0.jpg" alt="Splash Screen" />
   <img src="/assets/images/floating-1.png" alt="Splash floating" />
   <img src="/assets/images/logo.svg" alt="Logo" />
   ```

   **LoginPage.jsx:**

   ```jsx
   // Remove the {/* */} comments around:
   <img src="/assets/images/background-1.jpg" alt="Login Screen" />
   <img src="/assets/images/floating-2.png" alt="magical floating stars" />
   <img src="/assets/images/floating-1.png" alt="rocket" />
   ```

   **App.css:**

   ```css
   /* Uncomment the background-image lines: */
   background-image: url('/assets/images/background-desktop.jpg');
   background: url('/assets/images/background-3.jpg') no-repeat center center;
   ```

## Image Specifications

### Recommended Sizes

- **Backgrounds**: 1920x1080px or higher (JPEG, optimized)
- **Floating elements**: ~200-300px width (PNG with transparency)
- **Logo**: SVG (scalable) or PNG 512x512px

### Optimization Tips

- Compress JPEGs to reduce file size (80-90% quality)
- Use PNG for images requiring transparency
- Use SVG for logos and icons (best quality at any size)
- Keep total assets under 5MB for fast loading

## Current State

All image references are **commented out** with gradient fallbacks:

- ✅ **SplashScreen**: Purple gradient background
- ✅ **LoginPage**: Purple-to-pink gradient background
- ✅ **App backgrounds**: Solid colors as fallback

The app works perfectly without images, but adding them will enhance the visual experience!

## Example Structure

```
/public/
  /assets/
    /images/
      background-0.jpg          # Splash screen
      background-1.jpg          # Login page
      background-3.jpg          # App background (optional)
      background-desktop.jpg    # Desktop outer BG (optional)
      floating-1.png            # Rocket decoration
      floating-2.png            # Stars decoration
      logo.svg                  # Main logo
```

## Need Help?

If you don't have custom images yet:

1. The app works fine with gradient backgrounds
2. You can use placeholder images from services like:
   - Unsplash (https://unsplash.com)
   - Pexels (https://pexels.com)
3. Or create simple gradients/colors in Figma/Canva

Enjoy customizing your Pett Agent! 🐾
