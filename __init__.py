bl_info = {
    "name": "Easy Driver",
    "author": "NeoEmberArts",
    "version": (2, 0, 0), #MAJOR.MINOR.PATCH 7/20/26
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Rigging",
    "description": "Technical rigging made easier! Map transformations from a bone or obect to a custom pose/toggle/value/shapekey via automatically created drivers; Auto clamped and automatic mapping. Auto detects axis of change and the mimimum and maximum values.",
    "category": "Rigging",
    "tags": ["Rigging", "Animation"],
}

import bpy
from bpy.app.handlers import persistent
from . import classes
from . import ui
from .core_functions import scan_easydriver_drivers


@persistent
def _ez_driver_review_load_post(dummy):
    """Auto-refresh the Driver Review cache whenever a file is opened/reloaded.

    This makes the review list "just work" after opening a file - it's
    rebuilt fresh from what's actually in the file's drivers, rather than
    relying on any addon runtime state that wouldn't survive a reload.
    """
    try:
        scene = bpy.context.scene
        if scene is None:
            return
        results = scan_easydriver_drivers()
        review_list = scene.ez_driver_review_list
        review_list.clear()
        for r in results:
            item = review_list.add()
            item.id_name = r['id_name']
            item.id_type = r['id_type']
            item.data_path = r['data_path']
            item.array_index = r['array_index']
            item.curve_type = r['curve_type']
            item.source_desc = r['source_desc']
            item.target_desc = r['target_desc']
            item.expression = r.get('expression', '')
            item.expr_valid = r['expr_valid']
            item.source_valid = r['source_valid']
        scene.ez_driver_review_index = 0
    except Exception as e:
        print(f"Easy Driver: post-load driver scan failed: {e}")


def register():
    classes.register()
    ui.register()
    
    # Scene properties
    bpy.types.Scene.driver_recorder_props = bpy.props.PointerProperty(type=classes.DriverRecorderProperties)
    bpy.types.Scene.show_source = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.show_targets = bpy.props.BoolProperty(default=True)

    # Driver Review cache - stored on the Scene so it's saved with the file
    # and survives close/reopen, and refreshed automatically on load (below)
    # or on demand via the Scan button.
    bpy.types.Scene.ez_driver_review_list = bpy.props.CollectionProperty(type=classes.EZDriverReviewItem)
    bpy.types.Scene.ez_driver_review_index = bpy.props.IntProperty(default=0)

    # Custom Property Browser cache - rebuilt whenever the browse target
    # (object/bone) changes, via the update= callback on those properties.
    bpy.types.Scene.cp_browse_list = bpy.props.CollectionProperty(type=classes.CustomPropBrowserItem)
    bpy.types.Scene.cp_browse_index = bpy.props.IntProperty(default=0, update=classes._on_cp_browse_index_changed)

    # Multi-Source blend slots - a real CollectionProperty so it can use the
    # same native list widget (template_list) as the two lists above.
    bpy.types.Scene.multi_source_slots = bpy.props.CollectionProperty(type=classes.MultiSourceSlotItem)
    bpy.types.Scene.multi_source_slot_index = bpy.props.IntProperty(default=0)

    if _ez_driver_review_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_ez_driver_review_load_post)
    
    # Optional: Add fine tune mode property if not already in classes
    if not hasattr(bpy.types.Scene, 'source_fine_tune_mode'):
        bpy.types.Scene.source_fine_tune_mode = bpy.props.BoolProperty(default=False)

def unregister():
    if _ez_driver_review_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_ez_driver_review_load_post)

    ui.unregister()
    classes.unregister()
    # Clean up scene properties
    scene_props = [
        'driver_recorder_props',
        'show_source', 
        'show_targets',
        'source_fine_tune_mode',
        'ez_driver_review_list',
        'ez_driver_review_index',
        'cp_browse_list',
        'cp_browse_index',
        'multi_source_slots',
        'multi_source_slot_index',
    ]
    
    for prop in scene_props:
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)

if __name__ == "__main__":
    register()
