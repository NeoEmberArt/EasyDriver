bl_info = {
    "name": "Easy Driver",
    "author": "NeoEmberArts",
    "version": (1, 3, 0), #MAJOR.MINOR.PATCH - 8/30/2025
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Rigging",
    "description": "Technical rigging made easier! Map transformations from a bone or obect to a custom pose/toggle/value/shapekey via automatically created drivers; Auto clamped and automatic mapping. Auto detects axis of change and the mimimum and maximum values.",
    "category": "Rigging",
    "tags": ["Rigging", "Animation"],
}

import bpy

from . import classes
from . import ui

def register():
    classes.register()
    ui.register()
    
    # Scene properties
    bpy.types.Scene.driver_recorder_props = bpy.props.PointerProperty(type=classes.DriverRecorderProperties)
    bpy.types.Scene.show_source = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.show_targets = bpy.props.BoolProperty(default=True)

def unregister():
    ui.unregister()
    classes.unregister()
    if hasattr(bpy.types.Scene, 'driver_recorder_props'):
        del bpy.types.Scene.driver_recorder_props
    if hasattr(bpy.types.Scene, 'show_source'):
        del bpy.types.Scene.show_source
    if hasattr(bpy.types.Scene, 'show_targets'):
        del bpy.types.Scene.show_targets

if __name__ == "__main__":
    register()
