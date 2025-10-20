bl_info = {
    "name": "Easy Driver",
    "author": "NeoEmberArts",
    "version": (1, 5, 2), #MAJOR.MINOR.PATCH 09/31/2025
    "blender": (3, 0, 0),
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
    
    # Optional: Add fine tune mode property if not already in classes
    if not hasattr(bpy.types.Scene, 'source_fine_tune_mode'):
        bpy.types.Scene.source_fine_tune_mode = bpy.props.BoolProperty(default=False)

def unregister():
    ui.unregister()
    classes.unregister()
    # Clean up scene properties
    scene_props = [
        'driver_recorder_props',
        'show_source', 
        'show_targets',
        'source_fine_tune_mode'
    ]
    
    for prop in scene_props:
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)

if __name__ == "__main__":
    register()
