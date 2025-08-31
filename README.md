# Easy Driver - Technical Rigging Made Simple As Heck!
![Version](https://img.shields.io/badge/version-1.2.1-blue.svg)
![Blender](https://img.shields.io/badge/Blender-4.5%2B-orange.svg)
![License](https://img.shields.io/badge/license-MIT-yellow.svg)

### Consider Supporting developement of future plugins! 
https://embercat.gumroad.com/l/EasyDriver
The Gumroad page includes tutorial files and always hosts the most up-to-date version.
![example](https://public-files.gumroad.com/ycus5s2abf4cuahkn7l097ylq4rf)


## 🤔 What does this even do?
**Easy Driver** is a powerful Blender addon that eliminates the complexity of creating drivers manually.  
Perfect for:
- Rigging characters with shape key corrections and flexing
- Creating mechanical animations
- Building interactive controls  

This addon automatically detects movement patterns and creates perfectly mapped drivers in **seconds**.

---

## ✨ Key Features

### 🎯 Auto-Detection
- **Automatic Axis Detection** – Move your bone or object between two positions, and Easy Driver automatically detects which axis changed the most.  
- **Min/Max Value Recording** – Captures exact transformation ranges for perfect mapping.

---

### 🔄 Dual Source Support *(what's driving)*
- **Bone Transforms** – Use armature bones as driver sources: scale, rotation, or position.  
- **Object Transforms** – Use any object's location/rotation as input.  

---

### 🎛️ Multiple Target Types *(what you're driving)*

#### 🔹 Custom Pose Targets
- Record min/max poses for multiple bones simultaneously.  
- Automatically detects which bones changed and on which axes.  
- Perfect for facial rigs, mechanical parts, and complex deformations.

![example](https://public-files.gumroad.com/bgv9hlk0qvocir2ln44afsw3mmx1)

💡 *Example: custom poses via bone transformations (toe spread or corrective movement via a bone slider).*

#### 🔹 Shape Key Targets
- Browse and select shape keys from any mesh object.  
- Set custom min/max values (0.0 to 1.0) with **live feedback** so you know EXACTLY what it looks like.  
- Drive multiple shape keys at the same time easily.  

![example](https://public-files.gumroad.com/mxknqkhr5akczt3k2n69o9garsac)
💡 *Example: corrective shape keys.*

#### 🔹 Custom Path Targets
- Drive **ANY Blender property** using custom paths.  
- Built-in path validation.  
- Supports both float ranges and boolean toggles.  
- Multiple paths can be setup at once.  

![example](https://public-files.gumroad.com/sn9mvlvcm1s41rux4chshuh6rzj0)
💡 *Examples: hide/show IK bones, control modifier strength, toggle visibility, adjust constraint influence.*

---

## 🛠️ Extra Features
- **Linear Mapping with Clamping** – Smooth, predictable transitions (values stay in your set range).  
- **Batch Driver Creation** – Create multiple drivers simultaneously.  
- **Easy Driver Removal** – Clean up drivers with one click.  
- **Quaternion → Euler Conversion** – Automatically handles rotation mode conflicts.  

---

## 🎨 Perfect For
- **Character Rigging** – Facial controls, finger poses, corrective shapes  
- **Mechanical Rigs** – Pistons, gears, hydraulics, robotic joints  
- **Architectural Viz** – Doors, windows, moving parts  
- **Motion Graphics** – Abstract animations, UI elements  
- **Product Visualization** – Exploded views, configuration options  
