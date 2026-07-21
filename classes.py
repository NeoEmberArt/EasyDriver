import bpy
import re
import bpy_extras.view3d_utils
import math
from .core_functions import (
    get_selected_pose_bones, ensure_euler_rotation, ensure_object_euler_rotation,
    detect_significant_changes, get_to_bones_data, set_to_bones_data,
    get_shapekey_list_data, set_shapekey_list_data, get_path_list_data,
    set_path_list_data, validate_custom_path, createDriver, update_shapekey_value, auto_detect_path_type,
    update_fine_tune_min_value, update_fine_tune_max_value, update_fine_tune_axis, 
    update_fine_tune_object_min_value, update_fine_tune_object_max_value, 
    update_fine_tune_object_axis, parse_target_path, get_mirrored_name, mirror_source, mirror_pose_targets, mirror_shapekey_targets,
    auto_apply_armature_source, auto_apply_bone_source, auto_apply_object_source,
    scan_easydriver_drivers, resolve_easydriver_id_block, find_driver_fcurve,
    resolve_active_single_source,
    createMultiSourceDriver, get_selected_target_objects,
    resolve_multi_source_slot_for_constraint, scan_custom_properties,
    parse_custom_path_source
)

#---------------------------------------
# Custom Property Browser - shared refresh logic
#---------------------------------------
def _cp_browse_target(props):
    """Resolve the current browse target: a pose bone if custom_prop_bone is
    set on an armature, otherwise the object itself."""
    obj = props.custom_prop_source_object
    if not obj:
        return None
    bone_name = props.custom_prop_bone.strip()
    if bone_name and obj.type == 'ARMATURE' and bone_name in obj.pose.bones:
        return obj.pose.bones[bone_name]
    return obj


def _refresh_cp_browse_list(context):
    """Rebuild the Custom Property Browser list from whatever object/bone is
    currently selected. Called both by the manual Refresh button and
    automatically whenever the object/bone picker changes."""
    scene = context.scene if context else None
    if scene is None:
        return
    props = scene.driver_recorder_props
    target = _cp_browse_target(props)

    results = scan_custom_properties(target)
    scene.cp_browse_list.clear()
    for r in results:
        item = scene.cp_browse_list.add()
        item.prop_name = r['name']
        item.type_label = r['type_label']
        item.value_display = r['value_display']
    scene.cp_browse_index = 0


def _on_cp_browse_target_changed(self, context):
    _refresh_cp_browse_list(context)


def _on_cp_browse_index_changed(self, context):
    """Selecting a row in the Custom Property list IS picking the source -
    no separate 'Use Selected' button needed. Also tries to pick up the
    property's existing Min/Max UI range if it has one, so Min/Max are
    pre-filled for properties that were already range-configured."""
    scene = context.scene if context else None
    if scene is None:
        return
    browse_list = scene.cp_browse_list
    index = scene.cp_browse_index
    if not (0 <= index < len(browse_list)):
        return

    props = scene.driver_recorder_props
    item = browse_list[index]
    props.custom_prop_name = item.prop_name

    target = _cp_browse_target(props)
    if target is None or item.prop_name not in target:
        return
    try:
        ui_data = target.id_properties_ui(item.prop_name).as_dict()
        if 'min' in ui_data and 'max' in ui_data:
            ui_min, ui_max = ui_data['min'], ui_data['max']
            # Only adopt the range if it's a real finite, distinct range -
            # Blender defaults unset ranges to huge/inf sentinel values
            if ui_min not in (None,) and ui_max not in (None,) and ui_min != ui_max:
                if abs(ui_min) < 1e6 and abs(ui_max) < 1e6:
                    props.custom_prop_min = float(ui_min)
                    props.custom_prop_max = float(ui_max)
    except Exception:
        pass  # Bool/String properties, or ones without a UI range - fine, just skip

#---------------------------------------
# List Properties/Variables here
#---------------------------------------
class DriverRecorderProperties(bpy.types.PropertyGroup):
    path_recorded_min: bpy.props.BoolProperty(
        name="Path Min Recorded",
        default=False
    )
    
    path_recorded_max: bpy.props.BoolProperty(
        name="Path Max Recorded",
        default=False
    )
    # Add this where you register other scene properties
    manual_source_armature: bpy.props.PointerProperty(
        name="Armature",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE',
        description="Select armature for source bone",
        update=auto_apply_armature_source  # Remove lambda wrapper
    )

    manual_source_bone: bpy.props.StringProperty(
        name="Bone",
        description="Select bone from armature",
        update=auto_apply_bone_source  # Remove lambda wrapper
    )

    manual_source_object: bpy.props.PointerProperty(
        name="Object",
        type=bpy.types.Object,
        description="Select object as source",
        update=auto_apply_object_source  # Remove lambda wrapper
    )
    
    # Bone fine tune properties
    # NOTE: source_fine_tune_mode is registered on bpy.types.Scene in __init__.py register()
    fine_tune_min_value: bpy.props.FloatProperty(
        name="Min Value",
        update=update_fine_tune_min_value
    )
    fine_tune_max_value: bpy.props.FloatProperty(
        name="Max Value", 
        update=update_fine_tune_max_value
    )
    fine_tune_axis: bpy.props.EnumProperty(
        name="Axis",
        items=[
            ("LOC_X", "Loc X", "Location X"),
            ("LOC_Y", "Loc Y", "Location Y"), 
            ("LOC_Z", "Loc Z", "Location Z"),
            ("ROT_X", "Rot X", "Rotation X"),
            ("ROT_Y", "Rot Y", "Rotation Y"),
            ("ROT_Z", "Rot Z", "Rotation Z"),
            ("SCALE_X", "Scale X", "Scale X"),
            ("SCALE_Y", "Scale Y", "Scale Y"),
            ("SCALE_Z", "Scale Z", "Scale Z"),
        ],
        update=update_fine_tune_axis
    )
    # Object fine tune properties
    fine_tune_object_min_value: bpy.props.FloatProperty(
        name="Min Value",
        update=update_fine_tune_object_min_value
    )
    fine_tune_object_max_value: bpy.props.FloatProperty(
        name="Max Value",
        update=update_fine_tune_object_max_value
    )
    fine_tune_object_axis: bpy.props.EnumProperty(
        name="Axis",
        items=[
            ("LOC_X", "Loc X", "Location X"),
            ("LOC_Y", "Loc Y", "Location Y"),
            ("LOC_Z", "Loc Z", "Location Z"), 
            ("ROT_X", "Rot X", "Rotation X"),
            ("ROT_Y", "Rot Y", "Rotation Y"),
            ("ROT_Z", "Rot Z", "Rotation Z"),
            ("SCALE_X", "Scale X", "Scale X"),
            ("SCALE_Y", "Scale Y", "Scale Y"),
            ("SCALE_Z", "Scale Z", "Scale Z"),
        ],
        update=update_fine_tune_object_axis
    )

    """Property group for driver recording."""
    object_eyedropper_active: bpy.props.BoolProperty(
        name="Object Eyedropper Active",
        description="Whether the object eyedropper is currently active",
        default=False
    )
    # FROM source type selection
    from_source_type: bpy.props.EnumProperty(
        name="Source",
        items=[
            ('BONE', 'Object / Pose', 'Use an object or pose-bone transform as source'),
            ('SHAPEKEY', 'Shapekey', 'Use a shape key value as source'),
            ('CUSTOM_PROP', 'Custom Property', 'Use a custom property as source'),
            ('CUSTOM_PATH', 'Custom Path', 'Use any arbitrary property as source (Advanced) - node inputs, modifiers, scene properties, etc.'),
        ],
        default='BONE'
    )
    # Driver curve / mapping type - how the source range maps to the target range
    driver_curve_type: bpy.props.EnumProperty(
        name="Curve Type",
        description="How the source value maps to the target value across the range",
        items=[
            ('LINEAR', 'Linear',
             "Straight-line mapping, clamped to the target range. The default - constant "
             "rate of change from Min to Max. Use this unless you specifically need easing, "
             "looping, or extrapolation"),
            ('BEZIER', 'Bezier (Ease)',
             "Smooth ease-in/ease-out (smoothstep) mapping, clamped to the target range. "
             "Starts and ends gently with more motion in the middle - good for organic "
             "movement like blinks, ear flops, or any shape key that should feel less "
             "mechanical than a straight line"),
            ('EASE_IN', 'Ease In',
             "Starts slow, accelerates toward the end. Good for things that should feel "
             "like they're building up momentum - a wind-up before a snap, or motion that "
             "starts hesitant and commits harder as it goes"),
            ('EASE_OUT', 'Ease Out',
             "Starts fast, settles gently at the end. Good for motion that should feel "
             "like it's coming to rest - landing a pose, a blink closing, anything that "
             "shouldn't feel like it's slamming into its end value"),
            ('STEP', 'Step',
             "Snaps straight to Min or Max at the halfway point of the source range - no "
             "in-between values. Good for toggle-style behavior driven by a continuous "
             "source, like a pose-space switch or an on/off visual cue"),
            ('LOOPING', 'Looping',
             "Wraps the source value around the source range instead of clamping it, so "
             "the output repeats (sawtooth-style) as the source keeps increasing or "
             "decreasing past Min/Max. Use for continuously spinning sources (a wheel, a "
             "repeating cycle) where you want the target to cycle too instead of getting "
             "stuck at one end"),
            ('PINGPONG', 'Ping Pong',
             "Like Looping, but bounces back and forth between Min and Max (triangle wave) "
             "instead of snapping back to Min each cycle. Good for anything that should "
             "oscillate smoothly with a continuously increasing source - a wagging tail, "
             "a back-and-forth mechanical part"),
            ('INFINITE', 'Infinite',
             "Straight-line mapping that is NOT clamped - keeps extrapolating past Min/Max "
             "instead of flattening out. Use when the target should keep scaling/moving "
             "even if the source goes further than the recorded range (no ceiling or floor)"),
        ],
        default='LINEAR'
    )

    # ── Advanced: world/local space for bone & object transform sources ────
    source_use_world_space: bpy.props.BoolProperty(
        name="World Space",
        description="Read bone/object transform sources in world space instead of local space",
        default=False
    )

    # ── Advanced: multi-source blending ──────────────────────────────────
    multi_source_enabled: bpy.props.BoolProperty(
        name="Multi-Source",
        description="Combine two or more sources into a single driver input",
        default=False
    )
    multi_source_combine_mode: bpy.props.EnumProperty(
        name="Combine",
        description="How to combine the added sources into one value",
        items=[
            ('ADD', 'Add', 'Sum all sources together'),
            ('MULTIPLY', 'Multiply', 'Multiply all sources together'),
            ('SUBTRACT', 'Subtract', 'Subtract each later source from the first, in order'),
            ('DISTANCE', 'Distance', 'Absolute difference between exactly two sources'),
        ],
        default='ADD'
    )
    # Source slots now live in a real CollectionProperty (scene.multi_source_slots)
    # instead of a JSON blob, so they can use the same native list widget
    # (template_list) as the Driver Review and Custom Property Browser lists.
    # Expected range of the COMBINED value - the user sets this directly,
    # since combining sources changes the effective range (e.g. Add of two
    # 0..1 sources ranges 0..2).
    multi_source_from_min: bpy.props.FloatProperty(name="Min", default=0.0)
    multi_source_from_max: bpy.props.FloatProperty(name="Max", default=1.0)

    path_eyedropper_active: bpy.props.BoolProperty(
        name="Path Eyedropper Active",
        description="Whether the path eyedropper is currently listening for changes",
        default=False
    )
    # FROM bone data
    from_armature: bpy.props.StringProperty(name="From Armature")
    from_bone: bpy.props.StringProperty(name="From Bone")
    from_has_min: bpy.props.BoolProperty(default=False)
    from_has_max: bpy.props.BoolProperty(default=False)
    from_min_location: bpy.props.FloatVectorProperty(size=3)
    from_max_location: bpy.props.FloatVectorProperty(size=3)
    from_min_rotation: bpy.props.FloatVectorProperty(size=3)
    from_max_rotation: bpy.props.FloatVectorProperty(size=3)
    from_min_scale: bpy.props.FloatVectorProperty(size=3, default=(1.0, 1.0, 1.0))
    from_max_scale: bpy.props.FloatVectorProperty(size=3, default=(1.0, 1.0, 1.0))
    from_detected_axis: bpy.props.StringProperty(default="")  # e.g., "LOC X"
    
    # FROM object data
    from_object: bpy.props.StringProperty(name="From Object")
    from_object_has_min: bpy.props.BoolProperty(default=False)
    from_object_has_max: bpy.props.BoolProperty(default=False)
    from_object_min_location: bpy.props.FloatVectorProperty(size=3)
    from_object_max_location: bpy.props.FloatVectorProperty(size=3)
    from_object_min_rotation: bpy.props.FloatVectorProperty(size=3)
    from_object_max_rotation: bpy.props.FloatVectorProperty(size=3)
    from_object_min_scale: bpy.props.FloatVectorProperty(size=3, default=(1.0, 1.0, 1.0))
    from_object_max_scale: bpy.props.FloatVectorProperty(size=3, default=(1.0, 1.0, 1.0))
    from_object_detected_axis: bpy.props.StringProperty(default="")
    
    # Target type selection
    target_type: bpy.props.EnumProperty(
        name="Target Type",
        items=[
            ('CUSTOM_POSE', 'Custom Pose', 'Drive pose bone transforms (Pose Mode) or object transforms (Object Mode) - auto-detected'),
            ('SHAPEKEY_LIST', 'Shapekey List', 'Drive shape keys'),
            ('PATH_LIST', 'Path List', 'Drive custom paths')
        ],
        default='CUSTOM_POSE'
    )
    
    # Custom Pose data (JSON string)
    to_bones_data: bpy.props.StringProperty(default="{}")
    # Shapekey data - changed to StringProperty for searchable dropdown
    shapekey_target_object: bpy.props.StringProperty(
        name="Target Object",
        description="Object with shape keys"
    )
    
    shapekey_name: bpy.props.StringProperty(
        name="Shape Key",
        description="Shape key to drive"
    )
    
    shapekey_min_value: bpy.props.FloatProperty(
        name="Min Value",
        default=0.0,
        soft_min=-1.0,
        soft_max=1.0,
        update=lambda self, context: update_shapekey_value(self, context, True)
    )

    shapekey_max_value: bpy.props.FloatProperty(
        name="Max Value",
        default=1.0,
        soft_min=-1.0,
        soft_max=1.0,
        update=lambda self, context: update_shapekey_value(self, context, False)
    )
    
    # Shapekey list data (JSON string)
    shapekey_list_data: bpy.props.StringProperty(default="{}")
    
    # Path List data
    custom_path_input: bpy.props.StringProperty(
        name="Custom Path",
        description="Enter a custom Blender path (e.g., bpy.data.objects[\"Cube\"].hide_viewport)"
    )
    
    path_value_type: bpy.props.EnumProperty(
        name="Value Type",
        items=[
            ('FLOAT', 'Float Range', 'Use min/max float values'),
            ('BOOLEAN', 'Boolean Toggle', 'Use boolean on/off values')
        ],
        default='FLOAT'
    )
    
    path_min_value: bpy.props.FloatProperty(
        name="Min Value",
        default=0.0
    )
    
    path_max_value: bpy.props.FloatProperty(
        name="Max Value",
        default=1.0
    )
    
    path_false_value: bpy.props.FloatProperty(
        name="False Value",
        default=0.0,
        description="Value when driver input is at minimum"
    )
    
    path_true_value: bpy.props.FloatProperty(
        name="True Value", 
        default=1.0,
        description="Value when driver input is at maximum"
    )
    
    # Path list data (JSON string)
    path_list_data: bpy.props.StringProperty(default="{}")

    # ── Custom-property source ──────────────────────────────────────────────
    # Which object/armature owns the custom prop
    custom_prop_source_object: bpy.props.PointerProperty(
        name="Object / Armature",
        type=bpy.types.Object,
        description="Object or armature that owns the custom property",
        update=_on_cp_browse_target_changed
    )
    # Optional: drive a bone custom prop instead of the object itself
    custom_prop_bone: bpy.props.StringProperty(
        name="Bone (optional)",
        description="Leave empty to use the object custom prop; enter a bone name to use a bone custom prop",
        update=_on_cp_browse_target_changed
    )
    # Property name to create / use
    custom_prop_name: bpy.props.StringProperty(
        name="Property Name",
        default="my_driver",
        description="Name of the custom property (will be created if it does not exist)"
    )
    # Range
    custom_prop_min: bpy.props.FloatProperty(name="Min", default=0.0)
    custom_prop_max: bpy.props.FloatProperty(name="Max", default=1.0)
    # Internal: set to True once the property has been registered as source
    custom_prop_is_set: bpy.props.BoolProperty(default=False)

    # ── Shape-key source (use a shape key's value to drive something else) ──
    shapekey_src_object: bpy.props.PointerProperty(
        name="Object",
        type=bpy.types.Object,
        description="Mesh object that owns the shape key to use as a source"
    )
    shapekey_src_name: bpy.props.StringProperty(
        name="Shape Key",
        description="Name of the shape key whose value will drive the target"
    )
    shapekey_src_min: bpy.props.FloatProperty(name="Min", default=0.0)
    shapekey_src_max: bpy.props.FloatProperty(name="Max", default=1.0)
    # Internal: set to True once the shape key has been registered as source
    shapekey_src_is_set: bpy.props.BoolProperty(default=False)

    # ── Custom Path source (Advanced only - arbitrary property as a source,
    # using the same eyedropper/listener + record min/max flow as the
    # Path List target) ─────────────────────────────────────────────────────
    source_custom_path_input: bpy.props.StringProperty(
        name="Path",
        description="Arbitrary data path to use as the driver source (type it or use the eyedropper)"
    )
    source_path_eyedropper_active: bpy.props.BoolProperty(default=False)
    source_path_recorded_min: bpy.props.BoolProperty(default=False)
    source_path_recorded_max: bpy.props.BoolProperty(default=False)
    source_path_min_value: bpy.props.FloatProperty(name="Min", default=0.0)
    source_path_max_value: bpy.props.FloatProperty(name="Max", default=1.0)
    # Internal: set to True once the custom path has been registered as source
    source_custom_path_is_set: bpy.props.BoolProperty(default=False)

    # ── UI complexity tier ────────────────────────────────────────────────
    ui_complexity: bpy.props.EnumProperty(
        name="UI Level",
        description="How much of the interface to show",
        items=[
            ('BASIC', 'Basic', 'Just bone/object source recording, targets, and Create/Remove - no clutter'),
            ('MORE', 'More', 'Everything: custom property & shape key sources, curve type, Driver Review'),
            ('ADVANCED', 'Advanced', 'Everything in More, plus advanced options like Invert Range'),
        ],
        default='BASIC'
    )

    # ── Advanced option: invert the target range (swap min/max on create) ──
    invert_target_range: bpy.props.BoolProperty(
        name="Invert Range",
        description="Swap each target's Min/Max when creating drivers, reversing the direction of the mapping",
        default=False
    )

#---------------------------------------
# EyeDropper Functions
#---------------------------------------
class ANIM_OT_object_eyedropper(bpy.types.Operator):
    """Eyedropper tool to select objects by clicking in the viewport"""
    bl_idname = "anim.object_eyedropper"
    bl_label = "Object Eyedropper"
    bl_description = "Click on an object in the viewport to select it"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Property to specify which field to fill
    target_property: bpy.props.StringProperty(default="shapekey_target_object")
    
    def modal(self, context, event):
        context.area.tag_redraw()
        
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            # Allow navigation
            return {'PASS_THROUGH'}
        
        elif event.type == 'MOUSEMOVE':
            # Update cursor position
            return {'RUNNING_MODAL'}
        
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Perform raycast to find object under mouse
            result = self.raycast_object(context, event)
            if result:
                # Set the target property
                props = context.scene.driver_recorder_props
                setattr(props, self.target_property, result.name)
                
                self.report({'INFO'}, f"Selected object: {result.name}")
                self.finish(context)
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "No object under cursor")
        
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            # Cancel
            self.report({'INFO'}, "Object selection cancelled")
            self.finish(context)
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            # Set cursor to eyedropper
            context.window.cursor_modal_set('EYEDROPPER')
            
            # Set active state
            props = context.scene.driver_recorder_props
            props.object_eyedropper_active = True
            
            context.window_manager.modal_handler_add(self)
            self.report({'INFO'}, "Click on an object to select it (ESC to cancel)")
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}
    
    def finish(self, context):
        """Clean up when finished"""
        # Restore cursor
        context.window.cursor_modal_restore()
        
        # Clear active state
        props = context.scene.driver_recorder_props
        props.object_eyedropper_active = False
    
    def raycast_object(self, context, event):
        """Perform raycast to find object under mouse cursor"""
        # Get the region and region_3d
        region = context.region
        region_3d = context.space_data.region_3d
        
        # Get mouse coordinates
        coord = (event.mouse_region_x, event.mouse_region_y)
        
        # Convert 2D mouse position to 3D ray
        view_vector = bpy_extras.view3d_utils.region_2d_to_vector_3d(region, region_3d, coord)
        ray_origin = bpy_extras.view3d_utils.region_2d_to_origin_3d(region, region_3d, coord)
        
        # Perform raycast
        depsgraph = context.evaluated_depsgraph_get()
        result, location, normal, index, obj, matrix = context.scene.ray_cast(
            depsgraph, ray_origin, view_vector
        )
        
        if result and obj:
            # Return the original object (not evaluated)
            return bpy.data.objects.get(obj.name)
        
        return None



#---------------------------------------
# Constraint Operators
#---------------------------------------

class OBJECT_OT_limit_source_transforms(bpy.types.Operator):
    """Add limit constraints to source bone/object based on recorded min/max values"""
    bl_idname = "object.limit_source_transforms"
    bl_label = "Limit Source Transforms"
    bl_description = "Add limit constraints to prevent source from going beyond recorded min/max values"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        try:
            if props.multi_source_enabled:
                return self.execute_multi_source(props, context)

            # Automatically detect source type from recorded data
            if props.from_bone:
                success = self.limit_bone_transforms(props, context)
            elif props.from_object:
                success = self.limit_object_transforms(props, context)
            else:
                self.report({'ERROR'}, "No source configured. Please record MIN and MAX first.")
                return {'CANCELLED'}
            
            if success:
                self.report({'INFO'}, "Limit constraints added successfully")
            else:
                self.report({'ERROR'}, "Failed to add limit constraints")
                
        except Exception as e:
            self.report({'ERROR'}, f"Error adding constraints: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

    def execute_multi_source(self, props, context):
        """Apply the same Limit constraint logic to every transform-based
        slot in the multi-source blend, instead of the single active source."""
        slots = [
            {'label': s.label, 'kind': s.kind, 'from_path': s.from_path,
             'from_min': s.from_min, 'from_max': s.from_max, 'source_name': s.source_name}
            for s in context.scene.multi_source_slots
        ]
        if len(slots) < 2:
            self.report({'ERROR'}, "Multi-Source needs at least 2 added sources")
            return {'CANCELLED'}

        applied = 0
        skipped = []

        for slot in slots:
            label = slot.get('label', slot.get('source_name', '?'))
            info = resolve_multi_source_slot_for_constraint(slot)
            if not info:
                skipped.append(label)
                continue

            axis_info = info['axis_info']
            min_vec = [0.0, 0.0, 0.0]
            max_vec = [0.0, 0.0, 0.0]
            min_vec[axis_info['index']] = slot.get('from_min', 0.0)
            max_vec[axis_info['index']] = slot.get('from_max', 1.0)
            constraint_name = f"Limit_{axis_info['transform']}_{axis_info['axis']}"

            ok = False
            if info['is_bone']:
                armature = info['armature']
                if armature and info['bone_name'] in armature.pose.bones:
                    pose_bone = armature.pose.bones[info['bone_name']]
                    if axis_info['transform'] == 'LOC':
                        ok = self.add_location_limit(pose_bone, axis_info, min_vec, max_vec, constraint_name)
                    elif axis_info['transform'] == 'ROT':
                        ok = self.add_rotation_limit(pose_bone, axis_info, min_vec, max_vec, constraint_name)
                    elif axis_info['transform'] == 'SCALE':
                        ok = self.add_scale_limit(pose_bone, axis_info, min_vec, max_vec, constraint_name)
            else:
                obj = info['object']
                if obj:
                    if axis_info['transform'] == 'LOC':
                        ok = self.add_object_location_limit(obj, axis_info, min_vec, max_vec, constraint_name)
                    elif axis_info['transform'] == 'ROT':
                        ok = self.add_object_rotation_limit(obj, axis_info, min_vec, max_vec, constraint_name)
                    elif axis_info['transform'] == 'SCALE':
                        ok = self.add_object_scale_limit(obj, axis_info, min_vec, max_vec, constraint_name)

            if ok:
                applied += 1
            else:
                skipped.append(label)

        if applied == 0:
            self.report({'ERROR'}, "No transform-based sources to lock (custom property / shape key sources can't be constrained this way)")
            return {'CANCELLED'}

        msg = f"Added limit constraints to {applied} source(s)"
        if skipped:
            msg += f" — skipped (not a transform source): {', '.join(skipped)}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}

    def limit_bone_transforms(self, props, context):
        """Add limit constraints to bone"""
        if not props.from_armature or not props.from_bone:
            self.report({'ERROR'}, "No source bone configured")
            return False
        
        if not (props.from_has_min and props.from_has_max and props.from_detected_axis):
            self.report({'ERROR'}, "FROM bone needs MIN, MAX, and detected axis")
            return False
        
        # Get armature and bone
        armature = bpy.data.objects.get(props.from_armature)
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, f"Armature '{props.from_armature}' not found")
            return False
        
        # Check if bone exists
        if props.from_bone not in armature.pose.bones:
            self.report({'ERROR'}, f"Bone '{props.from_bone}' not found in armature")
            return False
        
        pose_bone = armature.pose.bones[props.from_bone]
        
        # Parse detected axis
        axis_info = self.parse_axis_info(props.from_detected_axis)
        if not axis_info:
            self.report({'ERROR'}, f"Could not parse axis info: {props.from_detected_axis}")
            return False
        
        # Add appropriate constraint
        constraint_name = f"Limit_{axis_info['transform']}_{axis_info['axis']}"
        
        if axis_info['transform'] == 'LOC':
            return self.add_location_limit(pose_bone, axis_info, props.from_min_location, props.from_max_location, constraint_name)
        elif axis_info['transform'] == 'ROT':
            return self.add_rotation_limit(pose_bone, axis_info, props.from_min_rotation, props.from_max_rotation, constraint_name)
        elif axis_info['transform'] == 'SCALE':
            return self.add_scale_limit(pose_bone, axis_info, props.from_min_scale, props.from_max_scale, constraint_name)
        return False

    def limit_object_transforms(self, props, context):
        """Add limit constraints to object"""
        if not props.from_object:
            self.report({'ERROR'}, "No source object configured")
            return False
        
        if not (props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis):
            self.report({'ERROR'}, "FROM object needs MIN, MAX, and detected axis")
            return False
        
        # Get object
        obj = bpy.data.objects.get(props.from_object)
        if not obj:
            self.report({'ERROR'}, f"Object '{props.from_object}' not found")
            return False
        
        # Parse detected axis
        axis_info = self.parse_axis_info(props.from_object_detected_axis)
        if not axis_info:
            self.report({'ERROR'}, f"Could not parse axis info: {props.from_object_detected_axis}")
            return False
        
        # Add appropriate constraint
        constraint_name = f"Limit_{axis_info['transform']}_{axis_info['axis']}"
        
        if axis_info['transform'] == 'LOC':
            return self.add_object_location_limit(obj, axis_info, props.from_object_min_location, props.from_object_max_location, constraint_name)
        elif axis_info['transform'] == 'ROT':
            return self.add_object_rotation_limit(obj, axis_info, props.from_object_min_rotation, props.from_object_max_rotation, constraint_name)
        elif axis_info['transform'] == 'SCALE':
            return self.add_object_scale_limit(obj, axis_info, props.from_object_min_scale, props.from_object_max_scale, constraint_name)
        
        return False

    def parse_axis_info(self, axis_string):
        """Parse axis string like 'LOC X' or 'ROT Y' into components"""
        if not axis_string:
            return None
        
        parts = axis_string.split()
        if len(parts) != 2:
            return None
        
        transform_type = parts[0]  # LOC, ROT, SCALE
        axis = parts[1]  # X, Y, Z
        
        # Map axis to index
        axis_map = {'X': 0, 'Y': 1, 'Z': 2}
        if axis not in axis_map:
            return None
        
        return {
            'transform': transform_type,
            'axis': axis,
            'index': axis_map[axis]
        }

    def get_sorted_values(self, min_val, max_val):
        """Ensure min is actually smaller than max, swap if needed"""
        if min_val > max_val:
            return max_val, min_val  # Swap them
        return min_val, max_val

    def add_location_limit(self, pose_bone, axis_info, min_loc, max_loc, constraint_name):
        """Add location limit constraint to pose bone"""
        # Remove existing constraint with same name
        if constraint_name in pose_bone.constraints:
            pose_bone.constraints.remove(pose_bone.constraints[constraint_name])
        
        # Add limit location constraint
        constraint = pose_bone.constraints.new('LIMIT_LOCATION')
        constraint.name = constraint_name
        
        axis_idx = axis_info['index']
        
        # Get properly sorted min/max values
        actual_min, actual_max = self.get_sorted_values(min_loc[axis_idx], max_loc[axis_idx])
        
        # Set limits for the specific axis
        if axis_info['axis'] == 'X':
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
        elif axis_info['axis'] == 'Y':
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
        elif axis_info['axis'] == 'Z':
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        constraint.owner_space = 'LOCAL'
        # Enable "Affect Transform" for location constraints
        constraint.use_transform_limit = True
        
        # Debug info
        print(f"Added location limit to {pose_bone.name} {axis_info['axis']}: {actual_min:.3f} to {actual_max:.3f}")
        return True

    def add_rotation_limit(self, pose_bone, axis_info, min_rot, max_rot, constraint_name):
        """Add rotation limit constraint to pose bone"""
        # Remove existing constraint with same name
        if constraint_name in pose_bone.constraints:
            pose_bone.constraints.remove(pose_bone.constraints[constraint_name])
        
        # Ensure bone is in Euler mode for proper constraint application
        original_mode = pose_bone.rotation_mode
        if original_mode == 'QUATERNION':
            temp_euler = pose_bone.rotation_quaternion.to_euler('XYZ')
            pose_bone.rotation_mode = 'XYZ'
            pose_bone.rotation_euler = temp_euler
        
        # Add limit rotation constraint
        constraint = pose_bone.constraints.new('LIMIT_ROTATION')
        constraint.name = constraint_name
        
        axis_idx = axis_info['index']
        
        # Get properly sorted min/max values (already in radians from recording)
        actual_min_rad, actual_max_rad = self.get_sorted_values(min_rot[axis_idx], max_rot[axis_idx])
        
        # Set limits for the specific axis - Blender limit rotation constraints use RADIANS
        if axis_info['axis'] == 'X':
            constraint.use_limit_x = True
            constraint.min_x = actual_min_rad
            constraint.max_x = actual_max_rad
        elif axis_info['axis'] == 'Y':
            constraint.use_limit_y = True
            constraint.min_y = actual_min_rad
            constraint.max_y = actual_max_rad
        elif axis_info['axis'] == 'Z':
            constraint.use_limit_z = True
            constraint.min_z = actual_min_rad
            constraint.max_z = actual_max_rad
        
        # Set constraint properties for proper rotation handling
        constraint.owner_space = 'LOCAL'
        # Enable "Affect Transform" for rotation constraints
        constraint.use_transform_limit = True
        
        # Debug info - convert to degrees just for display
        actual_min_deg = math.degrees(actual_min_rad)
        actual_max_deg = math.degrees(actual_max_rad)
        print(f"Added rotation limit to {pose_bone.name} {axis_info['axis']}: {actual_min_deg:.1f}° to {actual_max_deg:.1f}°")
        return True

    def add_object_location_limit(self, obj, axis_info, min_loc, max_loc, constraint_name):
        """Add location limit constraint to object"""
        # Remove existing constraint with same name
        for constraint in obj.constraints:
            if constraint.name == constraint_name:
                obj.constraints.remove(constraint)
                break
        
        # Add limit location constraint
        constraint = obj.constraints.new('LIMIT_LOCATION')
        constraint.name = constraint_name
        
        axis_idx = axis_info['index']
        
        # Get properly sorted min/max values
        actual_min, actual_max = self.get_sorted_values(min_loc[axis_idx], max_loc[axis_idx])
        
        # Set limits for the specific axis
        if axis_info['axis'] == 'X':
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
        elif axis_info['axis'] == 'Y':
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
        elif axis_info['axis'] == 'Z':
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        # Enable "Affect Transform" for object location constraints
        constraint.use_transform_limit = True
        
        # Debug info
        print(f"Added location limit to {obj.name} {axis_info['axis']}: {actual_min:.3f} to {actual_max:.3f}")
        return True

    def add_object_rotation_limit(self, obj, axis_info, min_rot, max_rot, constraint_name):
        """Add rotation limit constraint to object"""
        # Remove existing constraint with same name
        for constraint in obj.constraints:
            if constraint.name == constraint_name:
                obj.constraints.remove(constraint)
                break
        
        # Force object to use Euler rotation mode
        obj.rotation_mode = 'XYZ'
        
        # Add limit rotation constraint
        constraint = obj.constraints.new('LIMIT_ROTATION')
        constraint.name = constraint_name
        
        axis_idx = axis_info['index']
        
        # Get properly sorted min/max values (already in radians from recording)
        actual_min_rad, actual_max_rad = self.get_sorted_values(min_rot[axis_idx], max_rot[axis_idx])
        
        # Set limits for the specific axis - Blender rotation constraints use RADIANS
        if axis_info['axis'] == 'X':
            constraint.use_limit_x = True
            constraint.min_x = actual_min_rad
            constraint.max_x = actual_max_rad
        elif axis_info['axis'] == 'Y':
            constraint.use_limit_y = True
            constraint.min_y = actual_min_rad
            constraint.max_y = actual_max_rad
        elif axis_info['axis'] == 'Z':
            constraint.use_limit_z = True
            constraint.min_z = actual_min_rad
            constraint.max_z = actual_max_rad
        
        # Set constraint properties for proper rotation handling
        # Enable "Affect Transform" for object rotation constraints
        constraint.use_transform_limit = True
        
        # Debug info - convert to degrees just for display
        actual_min_deg = math.degrees(actual_min_rad)
        actual_max_deg = math.degrees(actual_max_rad)
        print(f"Added rotation limit to {obj.name} {axis_info['axis']}: {actual_min_deg:.1f}° to {actual_max_deg:.1f}°")
        return True
    
    def add_scale_limit(self, pose_bone, axis_info, min_scale, max_scale, constraint_name):
        """Add scale limit constraint to pose bone"""
        # Remove existing constraint with same name
        if constraint_name in pose_bone.constraints:
            pose_bone.constraints.remove(pose_bone.constraints[constraint_name])
        
        # Add limit scale constraint
        constraint = pose_bone.constraints.new('LIMIT_SCALE')
        constraint.name = constraint_name
        
        axis_idx = axis_info['index']
        
        # Get properly sorted min/max values
        actual_min, actual_max = self.get_sorted_values(min_scale[axis_idx], max_scale[axis_idx])
        
        # Set limits for the specific axis
        if axis_info['axis'] == 'X':
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
        elif axis_info['axis'] == 'Y':
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
        elif axis_info['axis'] == 'Z':
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        constraint.owner_space = 'LOCAL'
        # Enable "Affect Transform" for scale constraints
        constraint.use_transform_limit = True
        
        # Debug info
        print(f"Added scale limit to {pose_bone.name} {axis_info['axis']}: {actual_min:.3f} to {actual_max:.3f}")
        return True

    def add_object_scale_limit(self, obj, axis_info, min_scale, max_scale, constraint_name):
        """Add scale limit constraint to object"""
        # Remove existing constraint with same name
        for constraint in obj.constraints:
            if constraint.name == constraint_name:
                obj.constraints.remove(constraint)
                break
        
        # Add limit scale constraint
        constraint = obj.constraints.new('LIMIT_SCALE')
        constraint.name = constraint_name
        
        axis_idx = axis_info['index']
        
        # Get properly sorted min/max values
        actual_min, actual_max = self.get_sorted_values(min_scale[axis_idx], max_scale[axis_idx])
        
        # Set limits for the specific axis
        if axis_info['axis'] == 'X':
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
        elif axis_info['axis'] == 'Y':
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
        elif axis_info['axis'] == 'Z':
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        # Enable "Affect Transform" for object scale constraints
        constraint.use_transform_limit = True
        
        # Debug info
        print(f"Added scale limit to {obj.name} {axis_info['axis']}: {actual_min:.3f} to {actual_max:.3f}")
        return True


class OBJECT_OT_one_axis_source_limit(bpy.types.Operator):
    """Lock source to move/rotate only on the detected axis, preventing movement on other axes"""
    bl_idname = "object.one_axis_source_limit"
    bl_label = "Lock to One Axis Only"
    bl_description = "Lock source to only move/rotate on the detected axis, blocking all other axes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        try:
            if props.multi_source_enabled:
                return self.execute_multi_source(props, context)

            # Automatically detect source type from recorded data
            if props.from_bone:
                success = self.lock_bone_to_axis(props, context)
            elif props.from_object:
                success = self.lock_object_to_axis(props, context)
            else:
                self.report({'ERROR'}, "No source configured. Please record MIN and MAX first.")
                return {'CANCELLED'}
            
            if success:
                self.report({'INFO'}, "One-axis constraint added successfully")
            else:
                self.report({'ERROR'}, "Failed to add one-axis constraint")
                
        except Exception as e:
            self.report({'ERROR'}, f"Error adding one-axis constraint: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

    def execute_multi_source(self, props, context):
        """Apply the same one-axis lock logic to every transform-based slot
        in the multi-source blend, instead of the single active source."""
        slots = [
            {'label': s.label, 'kind': s.kind, 'from_path': s.from_path,
             'from_min': s.from_min, 'from_max': s.from_max, 'source_name': s.source_name}
            for s in context.scene.multi_source_slots
        ]
        if len(slots) < 2:
            self.report({'ERROR'}, "Multi-Source needs at least 2 added sources")
            return {'CANCELLED'}

        applied = 0
        skipped = []

        for slot in slots:
            label = slot.get('label', slot.get('source_name', '?'))
            info = resolve_multi_source_slot_for_constraint(slot)
            if not info:
                skipped.append(label)
                continue

            axis_info = info['axis_info']
            min_vec = [0.0, 0.0, 0.0]
            max_vec = [0.0, 0.0, 0.0]
            min_vec[axis_info['index']] = slot.get('from_min', 0.0)
            max_vec[axis_info['index']] = slot.get('from_max', 1.0)

            ok = False
            if info['is_bone']:
                armature = info['armature']
                if armature and info['bone_name'] in armature.pose.bones:
                    pose_bone = armature.pose.bones[info['bone_name']]
                    if axis_info['transform'] == 'LOC':
                        ok = self.add_bone_location_lock(pose_bone, axis_info, min_vec, max_vec)
                    elif axis_info['transform'] == 'ROT':
                        ok = self.add_bone_rotation_lock(pose_bone, axis_info, min_vec, max_vec)
                    elif axis_info['transform'] == 'SCALE':
                        ok = self.add_bone_scale_lock(pose_bone, axis_info, min_vec, max_vec)
            else:
                obj = info['object']
                if obj:
                    if axis_info['transform'] == 'LOC':
                        ok = self.add_object_location_lock(obj, axis_info, min_vec, max_vec)
                    elif axis_info['transform'] == 'ROT':
                        ok = self.add_object_rotation_lock(obj, axis_info, min_vec, max_vec)
                    elif axis_info['transform'] == 'SCALE':
                        ok = self.add_object_scale_lock(obj, axis_info, min_vec, max_vec)

            if ok:
                applied += 1
            else:
                skipped.append(label)

        if applied == 0:
            self.report({'ERROR'}, "No transform-based sources to lock (custom property / shape key sources can't be constrained this way)")
            return {'CANCELLED'}

        msg = f"Added one-axis constraints to {applied} source(s)"
        if skipped:
            msg += f" — skipped (not a transform source): {', '.join(skipped)}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}

    def lock_bone_to_axis(self, props, context):
        """Add constraints to lock bone to single axis movement"""
        if not props.from_armature or not props.from_bone:
            self.report({'ERROR'}, "No source bone configured")
            return False
        
        if not (props.from_has_min and props.from_has_max and props.from_detected_axis):
            self.report({'ERROR'}, "FROM bone needs MIN, MAX, and detected axis")
            return False
        
        # Get armature and bone
        armature = bpy.data.objects.get(props.from_armature)
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, f"Armature '{props.from_armature}' not found")
            return False
        
        if props.from_bone not in armature.pose.bones:
            self.report({'ERROR'}, f"Bone '{props.from_bone}' not found in armature")
            return False
        
        pose_bone = armature.pose.bones[props.from_bone]
        
        # Parse detected axis
        axis_info = self.parse_axis_info(props.from_detected_axis)
        if not axis_info:
            self.report({'ERROR'}, f"Could not parse axis info: {props.from_detected_axis}")
            return False
        
        if axis_info['transform'] == 'LOC':
            return self.add_bone_location_lock(pose_bone, axis_info, props.from_min_location, props.from_max_location)
        elif axis_info['transform'] == 'ROT':
            return self.add_bone_rotation_lock(pose_bone, axis_info, props.from_min_rotation, props.from_max_rotation)
        elif axis_info['transform'] == 'SCALE':
            return self.add_bone_scale_lock(pose_bone, axis_info, props.from_min_scale, props.from_max_scale)
        
        return False

    def lock_object_to_axis(self, props, context):
        """Add constraints to lock object to single axis movement"""
        if not props.from_object:
            self.report({'ERROR'}, "No source object configured")
            return False
        
        if not (props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis):
            self.report({'ERROR'}, "FROM object needs MIN, MAX, and detected axis")
            return False
        
        obj = bpy.data.objects.get(props.from_object)
        if not obj:
            self.report({'ERROR'}, f"Object '{props.from_object}' not found")
            return False
        
        # Parse detected axis
        axis_info = self.parse_axis_info(props.from_object_detected_axis)
        if not axis_info:
            self.report({'ERROR'}, f"Could not parse axis info: {props.from_object_detected_axis}")
            return False
        
        if axis_info['transform'] == 'LOC':
            return self.add_object_location_lock(obj, axis_info, props.from_object_min_location, props.from_object_max_location)
        elif axis_info['transform'] == 'ROT':
            return self.add_object_rotation_lock(obj, axis_info, props.from_object_min_rotation, props.from_object_max_rotation)
        elif axis_info['transform'] == 'SCALE':
            return self.add_object_scale_lock(obj, axis_info, props.from_object_min_scale, props.from_object_max_scale)
        
        return False

    def parse_axis_info(self, axis_string):
        """Parse axis string like 'LOC X' or 'ROT Y' into components"""
        if not axis_string:
            return None
        
        parts = axis_string.split()
        if len(parts) != 2:
            return None
        
        transform_type = parts[0]  # LOC, ROT, SCALE
        axis = parts[1]  # X, Y, Z
        
        axis_map = {'X': 0, 'Y': 1, 'Z': 2}
        if axis not in axis_map:
            return None
        
        return {
            'transform': transform_type,
            'axis': axis,
            'index': axis_map[axis]
        }

    def get_sorted_values(self, min_val, max_val):
        """Ensure min is actually smaller than max"""
        if min_val > max_val:
            return max_val, min_val
        return min_val, max_val

    def add_bone_location_lock(self, pose_bone, axis_info, min_loc, max_loc):
        """Lock bone location to only the detected axis"""
        constraint_name = f"OneAxis_LOC_{axis_info['axis']}"
        
        # Remove existing constraint
        if constraint_name in pose_bone.constraints:
            pose_bone.constraints.remove(pose_bone.constraints[constraint_name])
        
        # Add limit location constraint
        constraint = pose_bone.constraints.new('LIMIT_LOCATION')
        constraint.name = constraint_name
        constraint.owner_space = 'LOCAL'
        # Enable "Affect Transform" for bone location constraints
        constraint.use_transform_limit = True
        
        # Get current position to use as exact lock point for other axes
        current_loc = pose_bone.location.copy()
        
        # Get sorted min/max for the active axis
        axis_idx = axis_info['index']
        actual_min, actual_max = self.get_sorted_values(min_loc[axis_idx], max_loc[axis_idx])
        
        # Apply exact constraints - lock all axes except the detected one
        if axis_info['axis'] == 'X':
            # Allow X axis movement within recorded range
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
            # Lock Y axis to exact current value
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = current_loc[1]
            constraint.max_y = current_loc[1]
            # Lock Z axis to exact current value
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = current_loc[2]
            constraint.max_z = current_loc[2]
        elif axis_info['axis'] == 'Y':
            # Lock X axis to exact current value
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = current_loc[0]
            constraint.max_x = current_loc[0]
            # Allow Y axis movement within recorded range
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
            # Lock Z axis to exact current value
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = current_loc[2]
            constraint.max_z = current_loc[2]
        elif axis_info['axis'] == 'Z':
            # Lock X axis to exact current value
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = current_loc[0]
            constraint.max_x = current_loc[0]
            # Lock Y axis to exact current value
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = current_loc[1]
            constraint.max_y = current_loc[1]
            # Allow Z axis movement within recorded range
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        print(f"Locked {pose_bone.name} to {axis_info['axis']} axis only (range: {actual_min:.3f} to {actual_max:.3f})")
        return True

    def add_bone_rotation_lock(self, pose_bone, axis_info, min_rot, max_rot):
        """Lock bone rotation to only the detected axis"""
        constraint_name = f"OneAxis_ROT_{axis_info['axis']}"
        
        # Remove existing constraint
        if constraint_name in pose_bone.constraints:
            pose_bone.constraints.remove(pose_bone.constraints[constraint_name])
        
        # Ensure bone is in Euler mode for proper constraint application
        original_mode = pose_bone.rotation_mode
        if original_mode == 'QUATERNION':
            temp_euler = pose_bone.rotation_quaternion.to_euler('XYZ')
            pose_bone.rotation_mode = 'XYZ'
            pose_bone.rotation_euler = temp_euler
        
        # Add limit rotation constraint
        constraint = pose_bone.constraints.new('LIMIT_ROTATION')
        constraint.name = constraint_name
        constraint.owner_space = 'LOCAL'
        # Enable "Affect Transform" for bone rotation constraints
        constraint.use_transform_limit = True
        
        # Get current rotation to use as exact lock point for other axes
        current_rot = pose_bone.rotation_euler.copy()
        
        # Get sorted min/max for the active axis (in radians)
        axis_idx = axis_info['index']
        actual_min_rad, actual_max_rad = self.get_sorted_values(min_rot[axis_idx], max_rot[axis_idx])
        
        # Apply exact constraints - lock all axes except the detected one
        if axis_info['axis'] == 'X':
            # Allow X rotation within recorded range
            constraint.use_limit_x = True
            constraint.min_x = actual_min_rad
            constraint.max_x = actual_max_rad
            # Lock Y rotation to exact current value
            constraint.use_limit_y = True
            constraint.min_y = current_rot[1]
            constraint.max_y = current_rot[1]
            # Lock Z rotation to exact current value
            constraint.use_limit_z = True
            constraint.min_z = current_rot[2]
            constraint.max_z = current_rot[2]
        elif axis_info['axis'] == 'Y':
            # Lock X rotation to exact current value
            constraint.use_limit_x = True
            constraint.min_x = current_rot[0]
            constraint.max_x = current_rot[0]
            # Allow Y rotation within recorded range
            constraint.use_limit_y = True
            constraint.min_y = actual_min_rad
            constraint.max_y = actual_max_rad
            # Lock Z rotation to exact current value
            constraint.use_limit_z = True
            constraint.min_z = current_rot[2]
            constraint.max_z = current_rot[2]
        elif axis_info['axis'] == 'Z':
            # Lock X rotation to exact current value
            constraint.use_limit_x = True
            constraint.min_x = current_rot[0]
            constraint.max_x = current_rot[0]
            # Lock Y rotation to exact current value
            constraint.use_limit_y = True
            constraint.min_y = current_rot[1]
            constraint.max_y = current_rot[1]
            # Allow Z rotation within recorded range
            constraint.use_limit_z = True
            constraint.min_z = actual_min_rad
            constraint.max_z = actual_max_rad
        
        actual_min_deg = math.degrees(actual_min_rad)
        actual_max_deg = math.degrees(actual_max_rad)
        print(f"Locked {pose_bone.name} to {axis_info['axis']} rotation only (range: {actual_min_deg:.1f}° to {actual_max_deg:.1f}°)")
        return True

    def add_object_location_lock(self, obj, axis_info, min_loc, max_loc):
        """Lock object location to only the detected axis"""
        constraint_name = f"OneAxis_LOC_{axis_info['axis']}"
        
        # Remove existing constraint
        for constraint in obj.constraints:
            if constraint.name == constraint_name:
                obj.constraints.remove(constraint)
                break
        
        # Add limit location constraint
        constraint = obj.constraints.new('LIMIT_LOCATION')
        constraint.name = constraint_name
        # Enable "Affect Transform" for object location constraints
        constraint.use_transform_limit = True
        
        # Get current position to use as exact lock point for other axes
        current_loc = obj.location.copy()
        
        # Get sorted min/max for the active axis
        axis_idx = axis_info['index']
        actual_min, actual_max = self.get_sorted_values(min_loc[axis_idx], max_loc[axis_idx])
        
        # Apply exact constraints - lock all axes except the detected one
        # Apply exact constraints - lock all axes except the detected one
        if axis_info['axis'] == 'X':
            # Allow X movement within recorded range
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
            # Lock Y axis to exact current value
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = current_loc[1]
            constraint.max_y = current_loc[1]
            # Lock Z axis to exact current value
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = current_loc[2]
            constraint.max_z = current_loc[2]
        elif axis_info['axis'] == 'Y':
            # Lock X axis to exact current value
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = current_loc[0]
            constraint.max_x = current_loc[0]
            # Allow Y movement within recorded range
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
            # Lock Z axis to exact current value
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = current_loc[2]
            constraint.max_z = current_loc[2]
        elif axis_info['axis'] == 'Z':
            # Lock X axis to exact current value
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = current_loc[0]
            constraint.max_x = current_loc[0]
            # Lock Y axis to exact current value
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = current_loc[1]
            constraint.max_y = current_loc[1]
            # Allow Z movement within recorded range
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        print(f"Locked {obj.name} to {axis_info['axis']} axis only (range: {actual_min:.3f} to {actual_max:.3f})")
        return True

    def add_object_rotation_lock(self, obj, axis_info, min_rot, max_rot):
        """Lock object rotation to only the detected axis"""
        constraint_name = f"OneAxis_ROT_{axis_info['axis']}"
        
        # Remove existing constraint
        for constraint in obj.constraints:
            if constraint.name == constraint_name:
                obj.constraints.remove(constraint)
                break
        
        # Force object to use Euler rotation mode
        obj.rotation_mode = 'XYZ'
        
        # Add limit rotation constraint
        constraint = obj.constraints.new('LIMIT_ROTATION')
        constraint.name = constraint_name
        # Enable "Affect Transform" for object rotation constraints
        constraint.use_transform_limit = True
        
        # Get current rotation to use as exact lock point for other axes
        current_rot = obj.rotation_euler.copy()
        
        # Get sorted min/max for the active axis (in radians)
        axis_idx = axis_info['index']
        actual_min_rad, actual_max_rad = self.get_sorted_values(min_rot[axis_idx], max_rot[axis_idx])
        
        # Apply exact constraints - lock all axes except the detected one
        if axis_info['axis'] == 'X':
            # Allow X rotation within recorded range
            constraint.use_limit_x = True
            constraint.min_x = actual_min_rad
            constraint.max_x = actual_max_rad
            # Lock Y rotation to exact current value
            constraint.use_limit_y = True
            constraint.min_y = current_rot[1]
            constraint.max_y = current_rot[1]
            # Lock Z rotation to exact current value
            constraint.use_limit_z = True
            constraint.min_z = current_rot[2]
            constraint.max_z = current_rot[2]
        elif axis_info['axis'] == 'Y':
            # Lock X rotation to exact current value
            constraint.use_limit_x = True
            constraint.min_x = current_rot[0]
            constraint.max_x = current_rot[0]
            # Allow Y rotation within recorded range
            constraint.use_limit_y = True
            constraint.min_y = actual_min_rad
            constraint.max_y = actual_max_rad
            # Lock Z rotation to exact current value
            constraint.use_limit_z = True
            constraint.min_z = current_rot[2]
            constraint.max_z = current_rot[2]
        elif axis_info['axis'] == 'Z':
            # Lock X rotation to exact current value
            constraint.use_limit_x = True
            constraint.min_x = current_rot[0]
            constraint.max_x = current_rot[0]
            # Lock Y rotation to exact current value
            constraint.use_limit_y = True
            constraint.min_y = current_rot[1]
            constraint.max_y = current_rot[1]
            # Allow Z rotation within recorded range
            constraint.use_limit_z = True
            constraint.min_z = actual_min_rad
            constraint.max_z = actual_max_rad
        
        actual_min_deg = math.degrees(actual_min_rad)
        actual_max_deg = math.degrees(actual_max_rad)
        print(f"Locked {obj.name} to {axis_info['axis']} rotation only (range: {actual_min_deg:.1f}° to {actual_max_deg:.1f}°)")
        return True

    def add_bone_scale_lock(self, pose_bone, axis_info, min_scale, max_scale):
        """Lock bone scale to only the detected axis"""
        constraint_name = f"OneAxis_SCALE_{axis_info['axis']}"
        
        # Remove existing constraint
        if constraint_name in pose_bone.constraints:
            pose_bone.constraints.remove(pose_bone.constraints[constraint_name])
        
        # Add limit scale constraint
        constraint = pose_bone.constraints.new('LIMIT_SCALE')
        constraint.name = constraint_name
        constraint.owner_space = 'LOCAL'
        # Enable "Affect Transform" for bone scale constraints
        constraint.use_transform_limit = True
        
        # Get current scale to use as exact lock point for other axes
        current_scale = pose_bone.scale.copy()
        
        # Get sorted min/max for the active axis
        axis_idx = axis_info['index']
        actual_min, actual_max = self.get_sorted_values(min_scale[axis_idx], max_scale[axis_idx])
        
        # Apply exact constraints - lock all axes except the detected one
        if axis_info['axis'] == 'X':
            # Allow X scale within recorded range
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
            # Lock Y scale to exact current value
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = current_scale[1]
            constraint.max_y = current_scale[1]
            # Lock Z scale to exact current value
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = current_scale[2]
            constraint.max_z = current_scale[2]
        elif axis_info['axis'] == 'Y':
            # Lock X scale to exact current value
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = current_scale[0]
            constraint.max_x = current_scale[0]
            # Allow Y scale within recorded range
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
            # Lock Z scale to exact current value
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = current_scale[2]
            constraint.max_z = current_scale[2]
        elif axis_info['axis'] == 'Z':
            # Lock X scale to exact current value
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = current_scale[0]
            constraint.max_x = current_scale[0]
            # Lock Y scale to exact current value
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = current_scale[1]
            constraint.max_y = current_scale[1]
            # Allow Z scale within recorded range
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        print(f"Locked {pose_bone.name} to {axis_info['axis']} scale only (range: {actual_min:.3f} to {actual_max:.3f})")
        return True

    def add_object_scale_lock(self, obj, axis_info, min_scale, max_scale):
        """Lock object scale to only the detected axis"""
        constraint_name = f"OneAxis_SCALE_{axis_info['axis']}"
        
        # Remove existing constraint
        for constraint in obj.constraints:
            if constraint.name == constraint_name:
                obj.constraints.remove(constraint)
                break
        
        # Add limit scale constraint
        constraint = obj.constraints.new('LIMIT_SCALE')
        constraint.name = constraint_name
        # Enable "Affect Transform" for object scale constraints
        constraint.use_transform_limit = True
        
        # Get current scale to use as exact lock point for other axes
        current_scale = obj.scale.copy()
        
        # Get sorted min/max for the active axis
        axis_idx = axis_info['index']
        actual_min, actual_max = self.get_sorted_values(min_scale[axis_idx], max_scale[axis_idx])
        
        # Apply exact constraints - lock all axes except the detected one
        if axis_info['axis'] == 'X':
            # Allow X scale within recorded range
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
            # Lock Y scale to exact current value
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = current_scale[1]
            constraint.max_y = current_scale[1]
            # Lock Z scale to exact current value
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = current_scale[2]
            constraint.max_z = current_scale[2]
        elif axis_info['axis'] == 'Y':
            # Lock X scale to exact current value
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = current_scale[0]
            constraint.max_x = current_scale[0]
            # Allow Y scale within recorded range
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
            # Lock Z scale to exact current value
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = current_scale[2]
            constraint.max_z = current_scale[2]
        elif axis_info['axis'] == 'Z':
            # Lock X scale to exact current value
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = current_scale[0]
            constraint.max_x = current_scale[0]
            # Lock Y scale to exact current value
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = current_scale[1]
            constraint.max_y = current_scale[1]
            # Allow Z scale within recorded range
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        print(f"Locked {obj.name} to {axis_info['axis']} scale only (range: {actual_min:.3f} to {actual_max:.3f})")
        return True




#---------------------------------------
# Fine Tuning Operators
#---------------------------------------
class ANIM_OT_toggle_fine_tune(bpy.types.Operator):
    bl_idname = "anim.toggle_fine_tune"
    bl_label = "Toggle Fine Tune"
    bl_description = "Toggle fine tune mode for manual adjustment"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Toggle fine tune mode
        context.scene.source_fine_tune_mode = not context.scene.source_fine_tune_mode
        
        # If we're turning it on, initialize fine tune values and manual selection
        if context.scene.source_fine_tune_mode:
            if props.from_bone:
                self.init_bone_fine_tune(props, context)
            elif props.from_object:
                self.init_object_fine_tune(props, context)

        return {'FINISHED'}

    def init_bone_fine_tune(self, props, context):
        """Initialize fine tune values for bone."""
        # Initialize manual selection fields
        if props.from_armature:
            armature = bpy.data.objects.get(props.from_armature)
            props.manual_source_armature = armature
            props.manual_source_bone = props.from_bone
        
        # Clear object selection
        props.manual_source_object = None
        
        # Get current axis and values
        detected_axis = props.from_detected_axis
        
        # Set axis dropdown
        axis_map = {
            "LOC X": "LOC_X", "LOC Y": "LOC_Y", "LOC Z": "LOC_Z",
            "ROT X": "ROT_X", "ROT Y": "ROT_Y", "ROT Z": "ROT_Z",
            "SCALE X": "SCALE_X", "SCALE Y": "SCALE_Y", "SCALE Z": "SCALE_Z"
        }
        props.fine_tune_axis = axis_map.get(detected_axis, "LOC_X")
        
        # Get min/max values based on axis
        if "LOC" in detected_axis:
            axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
            props.fine_tune_min_value = props.from_min_location[axis_idx]
            props.fine_tune_max_value = props.from_max_location[axis_idx]
        elif "ROT" in detected_axis:
            axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
            props.fine_tune_min_value = props.from_min_rotation[axis_idx]
            props.fine_tune_max_value = props.from_max_rotation[axis_idx]
        elif "SCALE" in detected_axis:
            axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
            props.fine_tune_min_value = props.from_min_scale[axis_idx]
            props.fine_tune_max_value = props.from_max_scale[axis_idx]

    def init_object_fine_tune(self, props, context):
        """Initialize fine tune values for object."""
        # Initialize manual selection fields
        if props.from_object:
            obj = bpy.data.objects.get(props.from_object)
            props.manual_source_object = obj
        
        # Clear bone selection
        props.manual_source_armature = None
        props.manual_source_bone = ""
        
        # Get current axis and values
        detected_axis = props.from_object_detected_axis
        
        # Set axis dropdown
        axis_map = {
            "LOC X": "LOC_X", "LOC Y": "LOC_Y", "LOC Z": "LOC_Z",
            "ROT X": "ROT_X", "ROT Y": "ROT_Y", "ROT Z": "ROT_Z",
            "SCALE X": "SCALE_X", "SCALE Y": "SCALE_Y", "SCALE Z": "SCALE_Z"
        }
        props.fine_tune_object_axis = axis_map.get(detected_axis, "LOC_X")
        
        # Get min/max values based on axis
        if "LOC" in detected_axis:
            axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
            props.fine_tune_object_min_value = props.from_object_min_location[axis_idx]
            props.fine_tune_object_max_value = props.from_object_max_location[axis_idx]
        elif "ROT" in detected_axis:
            axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
            props.fine_tune_object_min_value = props.from_object_min_rotation[axis_idx]
            props.fine_tune_object_max_value = props.from_object_max_rotation[axis_idx]
        elif "SCALE" in detected_axis:
            axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
            props.fine_tune_object_min_value = props.from_object_min_scale[axis_idx]
            props.fine_tune_object_max_value = props.from_object_max_scale[axis_idx]
            """Initialize fine tune values for object."""
            # Get current axis and values
            detected_axis = props.from_object_detected_axis
            
            # Set axis dropdown
            axis_map = {
                "LOC X": "LOC_X", "LOC Y": "LOC_Y", "LOC Z": "LOC_Z",
                "ROT X": "ROT_X", "ROT Y": "ROT_Y", "ROT Z": "ROT_Z",
                "SCALE X": "SCALE_X", "SCALE Y": "SCALE_Y", "SCALE Z": "SCALE_Z"
            }
            props.fine_tune_object_axis = axis_map.get(detected_axis, "LOC_X")
            
            # Get min/max values based on axis
            if "LOC" in detected_axis:
                axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
                props.fine_tune_object_min_value = props.from_object_min_location[axis_idx]
                props.fine_tune_object_max_value = props.from_object_max_location[axis_idx]
            elif "ROT" in detected_axis:
                axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
                props.fine_tune_object_min_value = props.from_object_min_rotation[axis_idx]
                props.fine_tune_object_max_value = props.from_object_max_rotation[axis_idx]
            elif "SCALE" in detected_axis:
                axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
                props.fine_tune_object_min_value = props.from_object_min_scale[axis_idx]
                props.fine_tune_object_max_value = props.from_object_max_scale[axis_idx]

class ANIM_OT_close_fine_tune(bpy.types.Operator):
    bl_idname = "anim.close_fine_tune"
    bl_label = "Close Fine Tune"
    bl_description = "Close fine tune mode"

    def execute(self, context):
        context.scene.source_fine_tune_mode = False
        return {'FINISHED'}


#---------------------------------------
# Source>Recording Operators
#---------------------------------------
class ANIM_OT_record_from_min(bpy.types.Operator):
    bl_idname = "anim.record_from_min"
    bl_label = "Record Min Position"
    bl_description = "Record the current position/rotation as minimum (auto-detects bone/object mode)"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        obj = context.object
        
        if not obj:
            self.report({'ERROR'}, "Please select an object")
            return {'CANCELLED'}
        
        # Close fine tune mode when recording new values
        context.scene.source_fine_tune_mode = False
        
        # Auto-detect mode based on context
        if obj.type == 'ARMATURE' and obj.mode == 'POSE':
            return self.record_bone_min(context, props, obj)
        else:
            return self.record_object_min(context, props, obj)
    
    def record_bone_min(self, context, props, obj):
        """Record bone minimum values."""
        bone = context.active_pose_bone
        if not bone:
            self.report({'ERROR'}, "No active bone selected")
            return {'CANCELLED'}
        
        # Clear any existing object data
        self.clear_object_data(props)
        
        # Set as FROM bone and record min
        props.from_armature = obj.name
        props.from_bone = bone.name
        props.from_min_location = bone.location[:]
        props.from_min_scale = bone.scale[:]
        euler = ensure_euler_rotation(bone)
        props.from_min_rotation = (euler.x, euler.y, euler.z)
        props.from_has_min = True
        
        # Clear max and detected axis since we have a new bone
        props.from_has_max = False
        props.from_detected_axis = ""
        
        self.report({'INFO'}, f"Recorded MIN for bone {bone.name}")
        return {'FINISHED'}
    
    def record_object_min(self, context, props, obj):
        """Record object minimum values."""
        # Clear any existing bone data
        self.clear_bone_data(props)
        
        # Set as FROM object and record min
        props.from_object = obj.name
        props.from_object_min_location = obj.location[:]
        props.from_object_min_scale = obj.scale[:]
        euler = ensure_object_euler_rotation(obj)
        props.from_object_min_rotation = (euler.x, euler.y, euler.z)
        props.from_object_has_min = True
        
        # Clear max and detected axis since we have a new object
        props.from_object_has_max = False
        props.from_object_detected_axis = ""
        
        self.report({'INFO'}, f"Recorded MIN for object {obj.name}")
        return {'FINISHED'}
    
    def clear_bone_data(self, props):
        """Clear all bone-related data."""
        props.from_armature = ""
        props.from_bone = ""
        props.from_has_min = False
        props.from_has_max = False
        props.from_detected_axis = ""
    
    def clear_object_data(self, props):
        """Clear all object-related data."""
        props.from_object = ""
        props.from_object_has_min = False
        props.from_object_has_max = False
        props.from_object_detected_axis = ""

class ANIM_OT_record_from_max(bpy.types.Operator):
    bl_idname = "anim.record_from_max"
    bl_label = "Record Max Position"
    bl_description = "Record the current position/rotation as maximum and detect primary axis"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        obj = context.object
        
        if not obj:
            self.report({'ERROR'}, "Please select an object")
            return {'CANCELLED'}
        
        # Close fine tune mode when recording new values
        context.scene.source_fine_tune_mode = False
        
        # Determine mode based on what was recorded for min
        if props.from_bone:
            return self.record_bone_max(context, props, obj)
        elif props.from_object:
            return self.record_object_max(context, props, obj)
        else:
            self.report({'ERROR'}, "Please record MIN position first")
            return {'CANCELLED'}
    
    def record_bone_max(self, context, props, obj):
        """Record bone maximum values."""
        if not props.from_has_min or not props.from_bone:
            self.report({'ERROR'}, "Please record MIN position first")
            return {'CANCELLED'}
        
        if not obj or obj.name != props.from_armature or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'ERROR'}, "Please select the same armature in Pose Mode")
            return {'CANCELLED'}
        
        bone = obj.pose.bones.get(props.from_bone)
        if not bone:
            self.report({'ERROR'}, "FROM bone not found")
            return {'CANCELLED'}
        
        # Record max values
        props.from_max_location = bone.location[:]
        props.from_max_scale = bone.scale[:]
        euler = ensure_euler_rotation(bone)
        props.from_max_rotation = (euler.x, euler.y, euler.z)
        props.from_has_max = True
        
        # Detect primary axis
        self.detect_bone_axis(props)
        
        self.report({'INFO'}, f"Detected: {props.from_detected_axis}")
        return {'FINISHED'}
    
    def record_object_max(self, context, props, obj):
        """Record object maximum values."""
        if not props.from_object_has_min or not props.from_object:
            self.report({'ERROR'}, "Please record MIN position first")
            return {'CANCELLED'}
        
        if not obj or obj.name != props.from_object:
            self.report({'ERROR'}, "Please select the same object")
            return {'CANCELLED'}
        
        # Record max values
        props.from_object_max_location = obj.location[:]
        props.from_object_max_scale = obj.scale[:]
        euler = ensure_object_euler_rotation(obj)
        props.from_object_max_rotation = (euler.x, euler.y, euler.z)
        props.from_object_has_max = True
        
        # Detect primary axis
        self.detect_object_axis(props)
        
        self.report({'INFO'}, f"Detected: {props.from_object_detected_axis}")
        return {'FINISHED'}
    
    def detect_bone_axis(self, props):
        """Detect primary axis for bone transforms."""
        min_vals = {
            'location': props.from_min_location,
            'rotation': props.from_min_rotation,
            'scale': props.from_min_scale
        }
        max_vals = {
            'location': props.from_max_location,
            'rotation': props.from_max_rotation,
            'scale': props.from_max_scale
        }
        
        changes = detect_significant_changes(min_vals, max_vals)
        
        if changes:
            # Find the change with the largest difference
            largest_change = max(changes, key=lambda x: abs(x[3] - x[2]))
            transform_type, axis, _, _ = largest_change
            
            axis_names = ['X', 'Y', 'Z']
            if transform_type == 'location':
                props.from_detected_axis = f"LOC {axis_names[axis]}"
            elif transform_type == 'rotation_euler':
                props.from_detected_axis = f"ROT {axis_names[axis]}"
            elif transform_type == 'scale':
                props.from_detected_axis = f"SCALE {axis_names[axis]}"
            else:  # scale
                props.from_detected_axis = f"SCALE {axis_names[axis]}"
        else:
            props.from_detected_axis = "No significant change detected"
    
    def detect_object_axis(self, props):
        """Detect primary axis for object transforms."""
        min_vals = {
        'location': props.from_object_min_location,
        'rotation': props.from_object_min_rotation,
        'scale': props.from_object_min_scale  # Add this
        }
        max_vals = {
            'location': props.from_object_max_location,
            'rotation': props.from_object_max_rotation,
            'scale': props.from_object_max_scale  # Add this
        }
        
        changes = detect_significant_changes(min_vals, max_vals)
        
        if changes:
            # Find the change with the largest difference
            largest_change = max(changes, key=lambda x: abs(x[3] - x[2]))
            transform_type, axis, _, _ = largest_change
            
            axis_names = ['X', 'Y', 'Z']
            if transform_type == 'location':
                props.from_object_detected_axis = f"LOC {axis_names[axis]}"
            elif transform_type == 'rotation_euler':
                props.from_object_detected_axis = f"ROT {axis_names[axis]}"
            elif transform_type == 'scale':
                props.from_object_detected_axis = f"SCALE {axis_names[axis]}"
        else:
            props.from_object_detected_axis = "No significant change detected"

#---------------------------------------
# Target>Pose Operators
#---------------------------------------
class POSE_OT_remove_pose_bone(bpy.types.Operator):
    bl_idname = "pose.remove_pose_bone"
    bl_label = "Remove Target"
    bl_description = "Remove this bone or object from the target list"
   
    bone_name: bpy.props.StringProperty()
    
    def execute(self, context):
        props = context.scene.driver_recorder_props
        to_data = get_to_bones_data(props)
        
        if self.bone_name in to_data:
            del to_data[self.bone_name]
            set_to_bones_data(props, to_data)
            self.report({'INFO'}, f"Removed bone: {self.bone_name}")
        else:
            self.report({'WARNING'}, f"Bone not found: {self.bone_name}")
        
        return {'FINISHED'}


class ANIM_OT_edit_target_value(bpy.types.Operator):
    """Fine-tune one recorded axis's Min/Max on a Custom Pose target (bone or object) via popup"""
    bl_idname = "anim.edit_target_value"
    bl_label = "Edit Target Value"
    bl_description = "Fine-tune this axis's recorded Min/Max values"
    bl_options = {'REGISTER', 'UNDO'}

    key: bpy.props.StringProperty()
    change_index: bpy.props.IntProperty()
    edit_min: bpy.props.FloatProperty(name="Min")
    edit_max: bpy.props.FloatProperty(name="Max")

    def invoke(self, context, event):
        props = context.scene.driver_recorder_props
        to_data = get_to_bones_data(props)
        entry = to_data.get(self.key)
        if not entry:
            self.report({'ERROR'}, "Target not found")
            return {'CANCELLED'}

        changes = entry.get('detected_changes', [])
        if not (0 <= self.change_index < len(changes)):
            self.report({'ERROR'}, "Recorded axis not found")
            return {'CANCELLED'}

        self.edit_min = changes[self.change_index].get('min_val', 0.0)
        self.edit_max = changes[self.change_index].get('max_val', 1.0)
        return context.window_manager.invoke_props_dialog(self, width=250)

    def draw(self, context):
        props = context.scene.driver_recorder_props
        to_data = get_to_bones_data(props)
        entry = to_data.get(self.key, {})
        changes = entry.get('detected_changes', [])
        layout = self.layout

        display_name = entry.get('bone_name') or entry.get('object') or self.key
        if 0 <= self.change_index < len(changes):
            axis_label = changes[self.change_index].get('display', '')
            layout.label(text=f"{display_name} - {axis_label}", icon='GREASEPENCIL')

        row = layout.row(align=True)
        row.prop(self, "edit_min")
        row.prop(self, "edit_max")

    def execute(self, context):
        props = context.scene.driver_recorder_props
        to_data = get_to_bones_data(props)
        entry = to_data.get(self.key)
        if not entry:
            return {'CANCELLED'}

        changes = entry.get('detected_changes', [])
        if not (0 <= self.change_index < len(changes)):
            return {'CANCELLED'}

        if self.edit_min == self.edit_max:
            self.report({'ERROR'}, "Min and Max can't be equal")
            return {'CANCELLED'}

        changes[self.change_index]['min_val'] = self.edit_min
        changes[self.change_index]['max_val'] = self.edit_max
        entry['detected_changes'] = changes
        to_data[self.key] = entry
        set_to_bones_data(props, to_data)
        self.report({'INFO'}, "Target value updated")
        return {'FINISHED'}

class POSE_OT_record_to_min_pose(bpy.types.Operator):
    bl_idname = "pose.record_to_min_pose"
    bl_label = "Record MIN Pose"
    bl_description = "Record current pose as minimum. Works in Pose Mode (selected bones) or Object Mode (selected objects) - auto-detected"

    def execute(self, context):
        props = context.scene.driver_recorder_props

        if context.mode == 'OBJECT':
            return self._record_objects(context, props)

        _primary_obj, arm_bone_pairs = get_selected_pose_bones(context)

        if not arm_bone_pairs:
            self.report({'ERROR'}, "Please select bones in Pose Mode, or objects in Object Mode")
            return {'CANCELLED'}

        to_data = get_to_bones_data(props)
        recorded = 0

        for arm_obj, bone in arm_bone_pairs:
            # Unique key = "ArmatureName::BoneName" so same-named bones on
            # different rigs never collide.
            key = f"{arm_obj.name}::{bone.name}"

            location, rotation, scale = self.get_bone_transforms(bone)

            bone_data = to_data.get(key, {
                'armature': arm_obj.name,
                'bone_name': bone.name,
                'is_object': False,
                'has_min': False,
                'has_max': False,
                'min_location': [0, 0, 0],
                'max_location': [0, 0, 0],
                'min_rotation': [0, 0, 0],
                'max_rotation': [0, 0, 0],
                'detected_changes': []
            })

            # Always keep armature field in sync (key encodes it already, but
            # we still need it for the driver-creation lookup).
            bone_data['armature']   = arm_obj.name
            bone_data['bone_name']  = bone.name
            bone_data['min_location'] = location
            bone_data['min_rotation'] = rotation
            bone_data['min_scale']    = scale
            bone_data['has_min']      = True
            bone_data['has_max']      = False  # reset max on new min
            bone_data['detected_changes'] = []

            to_data[key] = bone_data
            recorded += 1

        set_to_bones_data(props, to_data)

        armature_names = sorted({arm.name for arm, _ in arm_bone_pairs})
        self.report({'INFO'},
            f"Recorded MIN pose for {recorded} bone(s) across {len(armature_names)} armature(s): "
            + ", ".join(armature_names))
        return {'FINISHED'}

    def _record_objects(self, context, props):
        """Object Mode counterpart to the bone recording above - same idea,
        just reading obj.location/rotation_euler/scale directly (no IK to
        worry about for plain objects)."""
        objects = get_selected_target_objects(context)
        if not objects:
            self.report({'ERROR'}, "Please select objects in Object Mode, or bones in Pose Mode")
            return {'CANCELLED'}

        to_data = get_to_bones_data(props)
        recorded = 0

        for obj in objects:
            key = f"OBJECT::{obj.name}"

            location = list(obj.location)
            rotation = list(obj.rotation_euler)
            scale = list(obj.scale)

            obj_data = to_data.get(key, {
                'object': obj.name,
                'is_object': True,
                'has_min': False,
                'has_max': False,
                'min_location': [0, 0, 0],
                'max_location': [0, 0, 0],
                'min_rotation': [0, 0, 0],
                'max_rotation': [0, 0, 0],
                'detected_changes': []
            })

            obj_data['object']       = obj.name
            obj_data['is_object']    = True
            obj_data['min_location'] = location
            obj_data['min_rotation'] = rotation
            obj_data['min_scale']    = scale
            obj_data['has_min']      = True
            obj_data['has_max']      = False
            obj_data['detected_changes'] = []

            to_data[key] = obj_data
            recorded += 1

        set_to_bones_data(props, to_data)

        obj_names = sorted(o.name for o in objects)
        self.report({'INFO'},
            f"Recorded MIN pose for {recorded} object(s): " + ", ".join(obj_names))
        return {'FINISHED'}
    
    def get_bone_transforms(self, bone):
        """Get bone transforms, handling IK constraints."""
        # Check if bone has IK constraints or is affected by IK
        has_ik = self.bone_has_ik_influence(bone)
        
        if has_ik:
            # For IK-controlled bones, get the actual world space rotation
            # and convert it to local space
            location, rotation, scale = self.get_ik_bone_transforms(bone)
        else:
            # Standard method for non-IK bones
            location = list(bone.location)
            scale = list(bone.scale)
            euler = ensure_euler_rotation(bone, True)
            rotation = list(euler)
        
        return location, rotation, scale
    
    def bone_has_ik_influence(self, bone):
        """Check if bone is influenced by IK constraints."""
        # Check if the bone itself has IK constraints
        for constraint in bone.constraints:
            if constraint.type in ['IK', 'SPLINE_IK', 'TRACK_TO', 'DAMPED_TRACK', 'LOCKED_TRACK']:
                return True
        
        # Check if bone is part of an IK chain by looking at children
        def check_ik_chain(check_bone, depth=0):
            if depth > 10:  # Prevent infinite recursion
                return False
            for child in check_bone.children:
                for constraint in child.constraints:
                    if constraint.type in ['IK', 'SPLINE_IK']:
                        # Check if this bone is the target or in the chain
                        if hasattr(constraint, 'target') and constraint.target == bone.id_data:
                            if hasattr(constraint, 'subtarget') and constraint.subtarget == bone.name:
                                return True
                        # Check chain length for IK
                        if constraint.type == 'IK' and hasattr(constraint, 'chain_count'):
                            if constraint.chain_count == 0 or depth < constraint.chain_count:
                                return True
                if check_ik_chain(child, depth + 1):
                    return True
            return False
        
        return check_ik_chain(bone)
    
    def get_ik_bone_transforms(self, bone):
        """Get transforms for IK-influenced bones."""
        import mathutils
        
        # Get the bone's current matrix in armature space
        armature = bone.id_data
        
        # Get the final matrix (after all constraints)
        if bone.parent:
            # Get relative to parent
            parent_matrix = bone.parent.matrix.inverted()
            relative_matrix = parent_matrix @ bone.matrix
        else:
            # No parent, use bone matrix directly
            relative_matrix = bone.matrix.copy()
        
        # Extract transforms from matrix
        location = relative_matrix.to_translation()
        rotation_quat = relative_matrix.to_quaternion()
        scale = relative_matrix.to_scale()
        
        # Convert quaternion to euler
        # Try to maintain current rotation mode if possible
        if bone.rotation_mode == 'QUATERNION':
            # Convert to XYZ euler for consistency
            euler = rotation_quat.to_euler('XYZ')
        elif bone.rotation_mode == 'AXIS_ANGLE':
            # Convert to XYZ euler
            euler = rotation_quat.to_euler('XYZ')
        else:
            # Use the bone's current rotation mode
            euler = rotation_quat.to_euler(bone.rotation_mode)
        
        return list(location), list(euler), list(scale)

class POSE_OT_record_to_max_pose(bpy.types.Operator):
    bl_idname = "pose.record_to_max_pose"
    bl_label = "Record MAX Pose"
    bl_description = "Record current pose as maximum and detect changes for all bones with MIN recorded"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        to_data = get_to_bones_data(props)

        # Build a dict: armature_name -> [key, ...] for all bones with MIN recorded.
        # Keys are "ArmatureName::BoneName" so same-named bones on different rigs
        # never collide. Object entries (is_object=True) are collected separately.
        bones_by_armature = {}
        object_keys = []
        for key, bone_data in to_data.items():
            if not bone_data.get('has_min', False):
                continue
            if bone_data.get('is_object'):
                object_keys.append(key)
            else:
                arm_name = bone_data.get('armature')
                if arm_name:
                    bones_by_armature.setdefault(arm_name, []).append(key)

        if not bones_by_armature and not object_keys:
            self.report({'ERROR'}, "No bones/objects with MIN pose recorded. Please record MIN pose first.")
            return {'CANCELLED'}

        bones_processed = 0
        bones_not_found = []
        armatures_processed = []

        # Process each armature separately so cross-armature setups work correctly
        for armature_name, keys in bones_by_armature.items():
            armature_obj = context.scene.objects.get(armature_name)
            if not armature_obj or armature_obj.type != 'ARMATURE':
                self.report({'WARNING'}, f"Armature '{armature_name}' not found in scene, skipping its bones")
                bones_not_found.extend(keys)
                continue

            armatures_processed.append(armature_name)

            for key in keys:
                bone_data = to_data[key]
                # bone_name is stored inside the dict; fall back to parsing the key
                bone_name = bone_data.get('bone_name') or key.split('::')[-1]
                bone = armature_obj.pose.bones.get(bone_name)
                if not bone:
                    bones_not_found.append(key)
                    continue

                bone_data = to_data[key]

                # Record max values using IK-aware method
                location, rotation, scale = self.get_bone_transforms(bone)

                bone_data['max_location'] = location
                bone_data['max_rotation'] = rotation
                bone_data['max_scale'] = scale
                bone_data['has_max'] = True

                # Detect which axes changed significantly between min and max
                min_vals = {
                    'location': bone_data['min_location'],
                    'rotation': bone_data['min_rotation'],
                    'scale': bone_data.get('min_scale', [1, 1, 1])
                }
                max_vals = {
                    'location': bone_data['max_location'],
                    'rotation': bone_data['max_rotation'],
                    'scale': bone_data['max_scale']
                }

                changes = detect_significant_changes(min_vals, max_vals)
                bone_data['detected_changes'] = []

                for transform_type, axis, min_val, max_val in changes:
                    axis_names = ['X', 'Y', 'Z']
                    if transform_type == 'location':
                        change_str = f"LOC {axis_names[axis]}"
                    elif transform_type == 'rotation_euler':
                        change_str = f"ROT {axis_names[axis]}"
                    elif transform_type == 'scale':
                        change_str = f"SCALE {axis_names[axis]}"
                    else:
                        change_str = f"{transform_type.upper()} {axis_names[axis]}"

                    bone_data['detected_changes'].append({
                        'type': transform_type,
                        'axis': axis,
                        'display': change_str,
                        'min_val': min_val,
                        'max_val': max_val
                    })

                bones_processed += 1

        # Process object entries (Object Mode recording)
        objects_processed = 0
        objects_not_found = []
        for key in object_keys:
            obj_data = to_data[key]
            obj_name = obj_data.get('object') or key.split('::')[-1]
            obj = bpy.data.objects.get(obj_name)
            if not obj:
                objects_not_found.append(obj_name)
                continue

            location = list(obj.location)
            rotation = list(obj.rotation_euler)
            scale = list(obj.scale)

            obj_data['max_location'] = location
            obj_data['max_rotation'] = rotation
            obj_data['max_scale'] = scale
            obj_data['has_max'] = True

            min_vals = {
                'location': obj_data['min_location'],
                'rotation': obj_data['min_rotation'],
                'scale': obj_data.get('min_scale', [1, 1, 1])
            }
            max_vals = {
                'location': obj_data['max_location'],
                'rotation': obj_data['max_rotation'],
                'scale': obj_data['max_scale']
            }

            changes = detect_significant_changes(min_vals, max_vals)
            obj_data['detected_changes'] = []

            for transform_type, axis, min_val, max_val in changes:
                axis_names = ['X', 'Y', 'Z']
                if transform_type == 'location':
                    change_str = f"LOC {axis_names[axis]}"
                elif transform_type == 'rotation_euler':
                    change_str = f"ROT {axis_names[axis]}"
                elif transform_type == 'scale':
                    change_str = f"SCALE {axis_names[axis]}"
                else:
                    change_str = f"{transform_type.upper()} {axis_names[axis]}"

                obj_data['detected_changes'].append({
                    'type': transform_type,
                    'axis': axis,
                    'display': change_str,
                    'min_val': min_val,
                    'max_val': max_val
                })

            objects_processed += 1

        set_to_bones_data(props, to_data)

        # Report results
        arm_label = ", ".join(armatures_processed) if armatures_processed else "unknown"
        extra = f", {objects_processed} object(s)" if objects_processed else ""
        if bones_not_found or objects_not_found:
            not_found_display = ", ".join(
                (d.get('bone_name') or k.split("::")[-1])
                for k, d in ((k, to_data.get(k, {})) for k in bones_not_found)
            )
            if objects_not_found:
                not_found_display = (not_found_display + ", " if not_found_display else "") + ", ".join(objects_not_found)
            self.report({'WARNING'},
                f"Recorded MAX pose for {bones_processed} bones{extra} across {len(armatures_processed)} armature(s). "
                f"Could not find: {not_found_display}")
        else:
            self.report({'INFO'},
                f"Recorded MAX pose for {bones_processed} bones{extra} across {len(armatures_processed)} armature(s): {arm_label}")

        return {'FINISHED'}
    
    def get_bone_transforms(self, bone):
        """Get bone transforms, handling IK constraints."""
        # Check if bone has IK constraints or is affected by IK
        has_ik = self.bone_has_ik_influence(bone)
        
        if has_ik:
            # For IK-controlled bones, get the actual world space rotation
            # and convert it to local space
            location, rotation, scale = self.get_ik_bone_transforms(bone)
        else:
            # Standard method for non-IK bones
            location = list(bone.location)
            scale = list(bone.scale)
            euler = ensure_euler_rotation(bone, True)
            rotation = list(euler)
        
        return location, rotation, scale
    
    def bone_has_ik_influence(self, bone):
        """Check if bone is influenced by IK constraints."""
        # Check if the bone itself has IK constraints
        for constraint in bone.constraints:
            if constraint.type in ['IK', 'SPLINE_IK', 'TRACK_TO', 'DAMPED_TRACK', 'LOCKED_TRACK']:
                return True
        
        # Check if bone is part of an IK chain by looking at children
        def check_ik_chain(check_bone, depth=0):
            if depth > 10:  # Prevent infinite recursion
                return False
            for child in check_bone.children:
                for constraint in child.constraints:
                    if constraint.type in ['IK', 'SPLINE_IK']:
                        # Check if this bone is the target or in the chain
                        if hasattr(constraint, 'target') and constraint.target == bone.id_data:
                            if hasattr(constraint, 'subtarget') and constraint.subtarget == bone.name:
                                return True
                        # Check chain length for IK
                        if constraint.type == 'IK' and hasattr(constraint, 'chain_count'):
                            if constraint.chain_count == 0 or depth < constraint.chain_count:
                                return True
                if check_ik_chain(child, depth + 1):
                    return True
            return False
        
        return check_ik_chain(bone)
    
    def get_ik_bone_transforms(self, bone):
        """Get transforms for IK-influenced bones."""
        import mathutils
        
        # Get the bone's current matrix in armature space
        armature = bone.id_data
        
        # Get the final matrix (after all constraints)
        if bone.parent:
            # Get relative to parent
            parent_matrix = bone.parent.matrix.inverted()
            relative_matrix = parent_matrix @ bone.matrix
        else:
            # No parent, use bone matrix directly
            relative_matrix = bone.matrix.copy()
        
        # Extract transforms from matrix
        location = relative_matrix.to_translation()
        rotation_quat = relative_matrix.to_quaternion()
        scale = relative_matrix.to_scale()
        
        # Convert quaternion to euler
        # Try to maintain current rotation mode if possible
        if bone.rotation_mode == 'QUATERNION':
            # Convert to XYZ euler for consistency
            euler = rotation_quat.to_euler('XYZ')
        elif bone.rotation_mode == 'AXIS_ANGLE':
            # Convert to XYZ euler
            euler = rotation_quat.to_euler('XYZ')
        else:
            # Use the bone's current rotation mode
            euler = rotation_quat.to_euler(bone.rotation_mode)
        
        return list(location), list(euler), list(scale)

#---------------------------------------
# Target>Shapekey Operators
#---------------------------------------
class MESH_OT_add_shapekey_target(bpy.types.Operator):
    bl_idname = "mesh.add_shapekey_target"
    bl_label = "Add Shape Key"
    bl_description = "Add the selected shape key to the target list"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.shapekey_target_object or not props.shapekey_name:
            self.report({'ERROR'}, "Please select an object and shape key")
            return {'CANCELLED'}
        
        # Validate object exists and has shape keys
        obj = bpy.data.objects.get(props.shapekey_target_object)
        if not obj:
            self.report({'ERROR'}, "Selected object not found")
            return {'CANCELLED'}
        
        if not (obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys):
            self.report({'ERROR'}, "Selected object has no shape keys")
            return {'CANCELLED'}
        
        # Validate shape key exists
        key_block = obj.data.shape_keys.key_blocks.get(props.shapekey_name)
        if not key_block:
            self.report({'ERROR'}, "Selected shape key not found")
            return {'CANCELLED'}
        
        shapekey_data = get_shapekey_list_data(props)
        
        # Create unique key for this shapekey
        key = f"{props.shapekey_target_object}:{props.shapekey_name}"
        
        # Check if already exists
        if key in shapekey_data:
            self.report({'WARNING'}, f"Shape key {props.shapekey_name} from {props.shapekey_target_object} already exists")
            return {'CANCELLED'}
        
        # Determine which source mode is actually active right now, so each
        # entry unambiguously records how it should be rebuilt later - this
        # matters once custom-property sources are mixed with bone/object
        # sources across different list entries.
        if props.custom_prop_is_set and props.custom_prop_source_object:
            entry_source_type = 'CUSTOM_PROP'
        elif props.shapekey_src_is_set and props.shapekey_src_object:
            entry_source_type = 'SHAPEKEY'
        elif props.from_bone and props.from_has_min and props.from_has_max and props.from_detected_axis:
            entry_source_type = 'BONE'
        elif props.from_object and props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis:
            entry_source_type = 'OBJECT'
        else:
            entry_source_type = ''

        shapekey_data[key] = {
            'object': props.shapekey_target_object,
            'shapekey': props.shapekey_name,
            'min_value': props.shapekey_min_value,
            'max_value': props.shapekey_max_value,
            # Snapshot source at add-time so each entry is self-contained
            'source_type': entry_source_type,
            'source_armature': props.from_armature,
            'source_bone': props.from_bone,
            'source_object': props.from_object,
            # Custom property source snapshot (object/bone name stored as
            # strings so it survives the JSON round-trip in shapekey_list_data)
            'source_custom_prop_object': props.custom_prop_source_object.name if props.custom_prop_source_object else '',
            'source_custom_prop_bone': props.custom_prop_bone,
            'source_custom_prop_name': props.custom_prop_name,
            'source_custom_prop_min': props.custom_prop_min,
            'source_custom_prop_max': props.custom_prop_max,
            # Shape-key source snapshot
            'source_shapekey_object': props.shapekey_src_object.name if props.shapekey_src_object else '',
            'source_shapekey_name': props.shapekey_src_name,
            'source_shapekey_min': props.shapekey_src_min,
            'source_shapekey_max': props.shapekey_src_max,
            'from_detected_axis': props.from_detected_axis,
            'from_min_location': list(props.from_min_location),
            'from_max_location': list(props.from_max_location),
            'from_min_rotation': list(props.from_min_rotation),
            'from_max_rotation': list(props.from_max_rotation),
            'from_min_scale':    list(props.from_min_scale),
            'from_max_scale':    list(props.from_max_scale),
            'from_object_detected_axis': props.from_object_detected_axis,
            'from_object_min_location': list(props.from_object_min_location),
            'from_object_max_location': list(props.from_object_max_location),
            'from_object_min_rotation': list(props.from_object_min_rotation),
            'from_object_max_rotation': list(props.from_object_max_rotation),
            'from_object_min_scale':    list(props.from_object_min_scale),
            'from_object_max_scale':    list(props.from_object_max_scale),
        }
        
        set_shapekey_list_data(props, shapekey_data)
        
        # Reset the shape key value to zero
        key_block.value = 0.0
        
        # Capture names before clearing
        added_name   = props.shapekey_name
        added_object = props.shapekey_target_object

        # Clear inputs after adding
        props.shapekey_target_object = ""
        props.shapekey_name = ""
        props.shapekey_min_value = 0.0
        props.shapekey_max_value = 1.0

        self.report({'INFO'}, f"Added '{added_name}' from '{added_object}' (reset to 0.0)")
        return {'FINISHED'}


class MESH_OT_edit_shapekey_target(bpy.types.Operator):
    bl_idname = "mesh.edit_shapekey_target"
    bl_label = "Edit Shape Key"
    bl_description = "Edit this shape key (loads values into inputs and removes from list)"

    key_to_edit: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        shapekey_data = get_shapekey_list_data(props)
        
        if self.key_to_edit not in shapekey_data:
            self.report({'ERROR'}, "Shape key not found in list")
            return {'CANCELLED'}
        
        # Get the data
        sk_data = shapekey_data[self.key_to_edit]
        
        # Load values into inputs
        props.shapekey_target_object = sk_data['object']
        props.shapekey_name = sk_data['shapekey']
        props.shapekey_min_value = sk_data['min_value']
        props.shapekey_max_value = sk_data['max_value']
        
        # Remove from list
        del shapekey_data[self.key_to_edit]
        set_shapekey_list_data(props, shapekey_data)
        
        self.report({'INFO'}, f"Loaded {sk_data['shapekey']} from {sk_data['object']} for editing")
        return {'FINISHED'}

class MESH_OT_remove_shapekey_target(bpy.types.Operator):
    bl_idname = "mesh.remove_shapekey_target"
    bl_label = "Remove"
    bl_description = "Remove this shape key from the list"

    key_to_remove: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        shapekey_data = get_shapekey_list_data(props)
        
        if self.key_to_remove in shapekey_data:
            sk_data = shapekey_data[self.key_to_remove]
            del shapekey_data[self.key_to_remove]
            set_shapekey_list_data(props, shapekey_data)
            self.report({'INFO'}, f"Removed {sk_data['shapekey']} from {sk_data['object']}")
        else:
            self.report({'ERROR'}, "Shape key not found in list")
        
        return {'FINISHED'}


#---------------------------------------
# Target>Path Operators
#---------------------------------------
class SCENE_OT_validate_path(bpy.types.Operator):
    bl_idname = "scene.validate_path"
    bl_label = "Validate Path"
    bl_description = "Test if the custom path is valid and accessible"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.custom_path_input:
            self.report({'ERROR'}, "Please enter a path to validate")
            return {'CANCELLED'}
        
        is_valid, result = validate_custom_path(props.custom_path_input)
        
        if is_valid:
            self.report({'INFO'}, f"Valid path! Type: {result}")
        else:
            self.report({'ERROR'}, f"Invalid path: {result}")
        
        return {'FINISHED'}



class ANIM_OT_path_eyedropper(bpy.types.Operator):
    """Eyedropper tool to capture property data paths by detecting changes"""
    bl_idname = "anim.path_eyedropper"
    bl_label = "Path Eyedropper"
    bl_description = "Click and change any property to capture its data path"
    bl_options = {'REGISTER', 'UNDO'}

    # Which props field to write the captured path into, and which bool
    # field tracks "listening" state - defaults match the original
    # Path List TARGET usage; the Custom Path SOURCE panel passes different
    # field names so both can reuse this same modal listener.
    target_field: bpy.props.StringProperty(default="custom_path_input")
    active_flag_field: bpy.props.StringProperty(default="path_eyedropper_active")

    _timer = None
    _initial_state = {}
    
    def modal(self, context, event):
        if event.type == 'ESC':
            self.cancel(context)
            return {'CANCELLED'}
        if event.type == 'TIMER':
            # Check for changes
            detected_path = self.detect_changes(context)
            if detected_path and self.is_valid_editable_path(detected_path):
                # Set the detected path
                props = context.scene.driver_recorder_props
                setattr(props, self.target_field, detected_path)
                
                self.report({'INFO'}, f"Captured path: {detected_path}")
                self.finish(context)
                return {'FINISHED'}
        return {'PASS_THROUGH'}

    
    def ignore(self, key):
        """Check if a custom property should be ignored"""
        # BlenderKit properties
        blenderkit_props = {
            'scatter1', 'scatter2', 'scatter3', 'scatter4', 'scatter5',
            'scattered', 'asset_id', 'asset_index', 'asset_data',
            'blenderkit', 'bkit_ratings', 'bkit_comments', 'bkit_last_updated',
            'bkit_downloads', 'bkit_installed_version', 'bkit_asset_type'
        }
        
        # General addon patterns
        addon_props = {
            'cycles_visibility', 'locked_shape_key', '_RNA_UI',
            'cycles', 'eevee', 'workbench', 'yp'
        }
        
        # Check exact matches
        if key in blenderkit_props or key in addon_props:
            return True
        
        # Check patterns (properties that start with certain prefixes)
        ignore_prefixes = ['bkit_', 'blenderkit_', '_', 'cycles_', 'eevee_', 'workbench_']
        if any(key.startswith(prefix) for prefix in ignore_prefixes):
            return True
        
        # Check patterns (properties that end with certain suffixes)
        ignore_suffixes = ['_data', '_cache', '_temp', '_internal']
        if any(key.endswith(suffix) for suffix in ignore_suffixes):
            return True
        
        return False

    def invoke(self, context, event):
        # Set listening state
        props = context.scene.driver_recorder_props
        setattr(props, self.active_flag_field, True)
        
        # Store initial state
        self.capture_initial_state(context)
        
        # Add timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        
        self.report({'INFO'}, "Eyedropper active - change any property to capture its path")
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        self.finish(context)
    
    def finish(self, context):
        # Clean up
        props = context.scene.driver_recorder_props
        setattr(props, self.active_flag_field, False)
        
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            self._timer = None
        
        # Clear state
        self._initial_state.clear()
    
    def safe_copy_value(self, value):
        """Safely copy a value, handling different types"""
        try:
            if hasattr(value, 'copy'):
                return value.copy()
            elif hasattr(value, '__len__') and not isinstance(value, str):
                return list(value)
            else:
                return value
        except:
            return value
    
    def safe_get_attr(self, obj, attr, default=None):
        """Safely get an attribute, returning default if it doesn't exist"""
        try:
            if hasattr(obj, attr):
                return getattr(obj, attr)
            return default
        except:
            return default
    
    def values_equal(self, val1, val2, tolerance=0.001):
        """Compare two values with tolerance for floats"""
        try:
            if hasattr(val1, '__len__') and hasattr(val2, '__len__') and not isinstance(val1, str):
                if len(val1) != len(val2):
                    return False
                return all(abs(a - b) <= tolerance for a, b in zip(val1, val2))
            elif isinstance(val1, float) or isinstance(val2, float):
                return abs(val1 - val2) <= tolerance
            else:
                return val1 == val2
        except:
            return val1 == val2
    
    def capture_initial_state(self, context):
        """Capture initial state of various properties"""
        self._initial_state.clear()
        
        # Monitor all objects
        for obj in context.view_layer.objects:
            obj_data = {}
            
            # Basic object properties
            obj_data['location'] = self.safe_copy_value(obj.location)
            obj_data['rotation_euler'] = self.safe_copy_value(obj.rotation_euler)
            obj_data['rotation_quaternion'] = self.safe_copy_value(obj.rotation_quaternion)
            obj_data['scale'] = self.safe_copy_value(obj.scale)
            obj_data['hide_viewport'] = obj.hide_viewport
            obj_data['hide_render'] = obj.hide_render
            obj_data['hide_select'] = obj.hide_select
            
            # Display properties
            if hasattr(obj, 'display'):
                display_props = ['show_shadows', 'show_in_front', 'show_wire', 'show_all_edges', 
                               'show_transparent', 'show_only_shape_key', 'show_bounds']
                obj_data['display'] = {}
                for prop in display_props:
                    val = self.safe_get_attr(obj.display, prop)
                    if val is not None:
                        obj_data['display'][prop] = val
            
            # Collision properties
            if hasattr(obj, 'collision') and obj.collision:
                collision_props = ['absorption', 'damping_factor', 'damping_random', 'friction_factor', 
                                 'friction_random', 'permeability', 'stickiness', 'thickness_inner', 
                                 'thickness_outer', 'use']
                obj_data['collision'] = {}
                for prop in collision_props:
                    val = self.safe_get_attr(obj.collision, prop)
                    if val is not None:
                        obj_data['collision'][prop] = self.safe_copy_value(val)
            
            # Rigid body properties
            if hasattr(obj, 'rigid_body') and obj.rigid_body:
                rb_props = ['mass', 'friction', 'restitution', 'linear_damping', 'angular_damping', 
                           'use_margin', 'collision_margin', 'kinematic', 'enabled']
                obj_data['rigid_body'] = {}
                for prop in rb_props:
                    val = self.safe_get_attr(obj.rigid_body, prop)
                    if val is not None:
                        obj_data['rigid_body'][prop] = self.safe_copy_value(val)
            
            # Constraints
            if obj.constraints:
                obj_data['constraints'] = {}
                for constraint in obj.constraints:
                    const_data = {
                        'influence': constraint.influence,
                        'mute': constraint.mute
                    }
                    # Add constraint-specific properties safely
                    constraint_props = ['target', 'subtarget', 'use_x', 'use_y', 'use_z']
                    for prop in constraint_props:
                        val = self.safe_get_attr(constraint, prop)
                        if val is not None:
                            const_data[prop] = val
                    obj_data['constraints'][constraint.name] = const_data
            
            # Pose bones (for armatures)
            if obj.type == 'ARMATURE' and obj.pose:
                obj_data['pose_bones'] = {}
                for pose_bone in obj.pose.bones:
                    pose_bone_data = {
                        'location': self.safe_copy_value(pose_bone.location),
                        'rotation_euler': self.safe_copy_value(pose_bone.rotation_euler),
                        'rotation_quaternion': self.safe_copy_value(pose_bone.rotation_quaternion),
                        'scale': self.safe_copy_value(pose_bone.scale),
                        'lock_location': self.safe_copy_value(pose_bone.lock_location),
                        'lock_rotation': self.safe_copy_value(pose_bone.lock_rotation),
                        'lock_scale': self.safe_copy_value(pose_bone.lock_scale)
                    }
                    
                    # Pose bone constraints
                    if pose_bone.constraints:
                        pose_bone_data['constraints'] = {}
                        for constraint in pose_bone.constraints:
                            const_data = {
                                'influence': constraint.influence,
                                'mute': constraint.mute
                            }
                            pose_bone_data['constraints'][constraint.name] = const_data
                    
                    obj_data['pose_bones'][pose_bone.name] = pose_bone_data
            
            # Shape keys
            if obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
                obj_data['shape_keys'] = {}
                for key_block in obj.data.shape_keys.key_blocks:
                    obj_data['shape_keys'][key_block.name] = {
                        'value': key_block.value,
                        'mute': key_block.mute
                    }
            
            # Modifiers
            if obj.modifiers:
                obj_data['modifiers'] = {}
                for modifier in obj.modifiers:
                    mod_data = {
                        'show_viewport': modifier.show_viewport,
                        'show_render': modifier.show_render
                    }
                    
                    # Common modifier properties
                    mod_props = ['strength', 'factor', 'offset', 'ratio', 'levels', 'angle_limit', 
                               'iterations', 'lambda_factor', 'lambda_border', 'use_x', 'use_y', 'use_z',
                               'width', 'segments', 'profile', 'limit_method', 'use_only_vertices',
                               'use_limit_to_selection', 'use_smooth', 'use_repeat', 'use_clamp']
                    for prop in mod_props:
                        val = self.safe_get_attr(modifier, prop)
                        if val is not None:
                            mod_data[prop] = self.safe_copy_value(val)
                    
                    obj_data['modifiers'][modifier.name] = mod_data
            
            # Custom properties
            obj_data['custom_props'] = {}
            for key in obj.keys():
                if key not in obj.bl_rna.properties.keys() and not self.ignore(key):
                    obj_data['custom_props'][key] = self.safe_copy_value(obj[key])
            
            self._initial_state[f"objects.{obj.name}"] = obj_data
        
        # Monitor cameras
        for camera in bpy.data.cameras:
            cam_data = {
                'lens': camera.lens,
                'sensor_width': camera.sensor_width,
                'sensor_height': camera.sensor_height,
                'clip_start': camera.clip_start,
                'clip_end': camera.clip_end,
                'type': camera.type,
                'ortho_scale': camera.ortho_scale,
                'shift_x': camera.shift_x,
                'shift_y': camera.shift_y,
                'dof': {}
            }
            
            # Depth of field properties
            if hasattr(camera, 'dof'):
                dof_props = ['use_dof', 'focus_distance', 'aperture_fstop', 'aperture_blades', 'aperture_rotation']
                for prop in dof_props:
                    val = self.safe_get_attr(camera.dof, prop)
                    if val is not None:
                        cam_data['dof'][prop] = val
            
            # Custom properties
            cam_data['custom_props'] = {}
            for key in camera.keys():
                if key not in camera.bl_rna.properties.keys() and not self.ignore(key):
                    try:
                        # Skip certain problematic properties
                        if key in ['cycles', 'eevee', 'workbench']:
                            continue
                        cam_data['custom_props'][key] = self.safe_copy_value(camera[key])
                    except:
                        pass
            
            self._initial_state[f"cameras.{camera.name}"] = cam_data
        
        # Monitor lights
        for light in bpy.data.lights:
            light_data = {
                'type': light.type,
                'energy': light.energy,
                'color': self.safe_copy_value(light.color),
                'use_shadow': light.use_shadow,
                'shadow_soft_size': light.shadow_soft_size,
                'cutoff_distance': light.cutoff_distance,
                'use_custom_distance': light.use_custom_distance
            }
            
            # Type-specific properties
            type_props = ['angle', 'spot_size', 'spot_blend', 'size', 'size_y', 'shape']
            for prop in type_props:
                val = self.safe_get_attr(light, prop)
                if val is not None:
                    light_data[prop] = val
            
            # Custom properties
            light_data['custom_props'] = {}
            for key in light.keys():
                if not self.ignore(key):
                    light_data['custom_props'][key] = self.safe_copy_value(light[key])
            
            self._initial_state[f"lights.{light.name}"] = light_data
        
        # Monitor armatures
        for armature in bpy.data.armatures:
            arm_data = {}
            
            # Armature display properties
            arm_props = ['show_bone_custom_shapes', 'show_names', 'show_axes', 'display_type']
            for prop in arm_props:
                val = self.safe_get_attr(armature, prop)
                if val is not None:
                    arm_data[prop] = val
            
            # Bone collections visibility
            arm_data['collections'] = {}
            collections_attr = None
            if hasattr(armature, 'collections_all'):
                collections_attr = 'collections_all'
            elif hasattr(armature, 'collections'):
                collections_attr = 'collections'
            
            if collections_attr:
                try:
                    collections = getattr(armature, collections_attr)
                    for collection in collections:
                        arm_data['collections'][collection.name] = {
                            'is_visible': collection.is_visible,
                            'attr_name': collections_attr
                        }
                except:
                    pass
            
            # Bone properties
            arm_data['bones'] = {}
            for bone in armature.bones:
                bone_props = ['hide_select', 'hide', 'use_deform', 'use_inherit_rotation', 
                             'use_inherit_scale', 'use_local_location', 'use_relative_parent',
                             'envelope_distance', 'envelope_weight', 'head_radius', 'tail_radius']
                bone_data = {}
                for prop in bone_props:
                    val = self.safe_get_attr(bone, prop)
                    if val is not None:
                        bone_data[prop] = self.safe_copy_value(val)
                arm_data['bones'][bone.name] = bone_data
            
            # Custom properties
            arm_data['custom_props'] = {}
            for key in armature.keys():
                if not self.ignore(key):
                    arm_data['custom_props'][key] = self.safe_copy_value(armature[key])
            
            self._initial_state[f"armatures.{armature.name}"] = arm_data
        
        # Monitor materials
        for mat in bpy.data.materials:
            mat_data = {}
            
            # Basic material properties - check each one safely
            mat_props = ['use_backface_culling', 'blend_method', 'shadow_method', 'alpha_threshold', 
                        'use_screen_refraction', 'refraction_depth', 'use_sss_translucency']
            for prop in mat_props:
                val = self.safe_get_attr(mat, prop)
                if val is not None:
                    mat_data[prop] = val
            
            # Node tree
            if mat.use_nodes and mat.node_tree:
                mat_data['nodes'] = {}
                
                for node in mat.node_tree.nodes:
                    node_data = {}
                    
                    # Node properties - check safely
                    node_props = ['mute', 'hide', 'factor', 'inputs_clear', 'use_clamp', 
                                 'operation', 'blend_type', 'fac', 'roughness', 'anisotropy', 
                                 'rotation', 'normal', 'clearcoat', 'clearcoat_roughness', 
                                 'ior', 'transmission', 'emission_strength']
                    for prop in node_props:
                        val = self.safe_get_attr(node, prop)
                        if val is not None:
                            node_data[prop] = self.safe_copy_value(val)
                    
                    # Input values
                    if hasattr(node, 'inputs'):
                        node_data['inputs'] = {}
                        for i, input_socket in enumerate(node.inputs):
                            if hasattr(input_socket, 'default_value'):
                                try:
                                    node_data['inputs'][i] = self.safe_copy_value(input_socket.default_value)
                                except:
                                    pass
                    
                    # Output values (some nodes have editable outputs)
                    if hasattr(node, 'outputs'):
                        node_data['outputs'] = {}
                        for i, output_socket in enumerate(node.outputs):
                            if hasattr(output_socket, 'default_value'):
                                try:
                                    node_data['outputs'][i] = self.safe_copy_value(output_socket.default_value)
                                except:
                                    pass
                    
                    # ColorRamp elements
                    if hasattr(node, 'color_ramp') and node.color_ramp:
                        try:
                            node_data['color_ramp'] = {'elements': {}}
                            for i, element in enumerate(node.color_ramp.elements):
                                node_data['color_ramp']['elements'][i] = {
                                    'position': element.position,
                                    'color': self.safe_copy_value(element.color)
                                }
                        except:
                            pass
                    
                    mat_data['nodes'][node.name] = node_data
            
            # Custom properties
            mat_data['custom_props'] = {}
            for key in mat.keys():
                mat_data['custom_props'][key] = self.safe_copy_value(mat[key])
            
            self._initial_state[f"materials.{mat.name}"] = mat_data
        
        # Monitor scenes
        for scene in bpy.data.scenes:
            scene_data = {}
            
            # Frame properties
            scene_data['frame_current'] = scene.frame_current
            scene_data['frame_start'] = scene.frame_start
            scene_data['frame_end'] = scene.frame_end
            scene_data['frame_step'] = scene.frame_step
            
            # Physics properties
            scene_data['use_gravity'] = scene.use_gravity
            scene_data['gravity'] = self.safe_copy_value(scene.gravity)
            
            # Render properties
            scene_data['render'] = {}
            render_props = ['resolution_x', 'resolution_y', 'resolution_percentage', 'fps', 'fps_base']
            for prop in render_props:
                val = self.safe_get_attr(scene.render, prop)
                if val is not None:
                    scene_data['render'][prop] = val
            
            # Render engine properties
            if hasattr(scene, 'eevee'):
                eevee_props = ['taa_samples', 'taa_render_samples', 'use_taa_reprojection', 
                              'use_ssr', 'use_ssr_refraction', 'use_bloom', 'use_motion_blur',
                              'motion_blur_shutter', 'bloom_threshold', 'bloom_knee', 'bloom_radius']
                scene_data['eevee'] = {}
                for prop in eevee_props:
                    val = self.safe_get_attr(scene.eevee, prop)
                    if val is not None:
                        scene_data['eevee'][prop] = val
            
            if hasattr(scene, 'cycles'):
                cycles_props = ['samples', 'preview_samples', 'use_denoising', 'denoiser',
                               'max_bounces', 'diffuse_bounces', 'glossy_bounces', 'transmission_bounces']
                scene_data['cycles'] = {}
                for prop in cycles_props:
                    val = self.safe_get_attr(scene.cycles, prop)
                    if val is not None:
                        scene_data['cycles'][prop] = val
            
            # World properties
            if scene.world:
                scene_data['world'] = {
                    'use_nodes': scene.world.use_nodes,
                    'color': self.safe_copy_value(scene.world.color)
                }
                
                # World node tree
                if scene.world.use_nodes and scene.world.node_tree:
                    scene_data['world']['nodes'] = {}
                    for node in scene.world.node_tree.nodes:
                        node_data = {}
                        if hasattr(node, 'inputs'):
                            node_data['inputs'] = {}
                            for i, input_socket in enumerate(node.inputs):
                                if hasattr(input_socket, 'default_value'):
                                    try:
                                        node_data['inputs'][i] = self.safe_copy_value(input_socket.default_value)
                                    except:
                                        pass
                        scene_data['world']['nodes'][node.name] = node_data
            
            self._initial_state[f"scenes.{scene.name}"] = scene_data

    def is_valid_editable_path(self, path_string):
        """Check if a data path is valid and editable"""
        try:
            # Try to evaluate the path
            result = eval(path_string)
            
            # Check if it's a read-only property
            # Extract the object and property from the path
            parts = path_string.split('.')
            
            # Navigate to the property to check if it's editable
            if len(parts) >= 2:
                # Build the object path (everything except the last property)
                obj_path = '.'.join(parts[:-1])
                prop_name = parts[-1]
                
                # Handle array indexing
                if '[' in prop_name:
                    prop_name = prop_name.split('[')[0]
                
                try:
                    obj = eval(obj_path)
                    
                    # Check if the property exists in RNA
                    if hasattr(obj, 'bl_rna') and hasattr(obj.bl_rna, 'properties'):
                        if prop_name in obj.bl_rna.properties:
                            prop = obj.bl_rna.properties[prop_name]
                            
                            # Check if property is read-only
                            if prop.is_readonly:
                                return False
                            
                            # Check if property is animatable (can be keyframed/driven)
                            if hasattr(prop, 'is_animatable') and not prop.is_animatable:
                                return False
                    
                    # Try to set the value to itself (test if it's writable)
                    current_value = result
                    exec(f"{path_string} = current_value")
                    
                    return True
                    
                except (AttributeError, TypeError, KeyError):
                    return False
            
            return True
            
        except (SyntaxError, NameError, AttributeError, TypeError, KeyError, IndexError):
            return False
    def detect_changes(self, context):
        """Detect what property has changed and return its data path"""
        
        # Check objects
        for obj in context.view_layer.objects:
            obj_key = f"objects.{obj.name}"
            if obj_key not in self._initial_state:
                continue
                
            initial_obj = self._initial_state[obj_key]
            
            # Basic properties
            basic_props = ['location', 'rotation_euler', 'rotation_quaternion', 'scale', 'hide_viewport', 'hide_render', 'hide_select']
            for prop in basic_props:
                if prop in initial_obj:
                    current_val = getattr(obj, prop)
                    if not self.values_equal(current_val, initial_obj[prop]):
                        # Check for array index
                        if hasattr(current_val, '__len__') and not isinstance(current_val, str):
                            for i, (curr, init) in enumerate(zip(current_val, initial_obj[prop])):
                                if not self.values_equal(curr, init):
                                    return f'bpy.data.objects["{obj.name}"].{prop}[{i}]'
                        return f'bpy.data.objects["{obj.name}"].{prop}'
            
            # Display properties
            if 'display' in initial_obj and hasattr(obj, 'display'):
                for prop, initial_val in initial_obj['display'].items():
                    current_val = self.safe_get_attr(obj.display, prop)
                    if current_val is not None and current_val != initial_val:
                        return f'bpy.data.objects["{obj.name}"].display.{prop}'
            
            # Collision properties
            if 'collision' in initial_obj and hasattr(obj, 'collision') and obj.collision:
                for prop, initial_val in initial_obj['collision'].items():
                    current_val = self.safe_get_attr(obj.collision, prop)
                    if current_val is not None and not self.values_equal(current_val, initial_val):
                        return f'bpy.data.objects["{obj.name}"].collision.{prop}'
            
            # Rigid body properties
            if 'rigid_body' in initial_obj and hasattr(obj, 'rigid_body') and obj.rigid_body:
                for prop, initial_val in initial_obj['rigid_body'].items():
                    current_val = self.safe_get_attr(obj.rigid_body, prop)
                    if current_val is not None and not self.values_equal(current_val, initial_val):
                        return f'bpy.data.objects["{obj.name}"].rigid_body.{prop}'
            
            # Constraints
            if 'constraints' in initial_obj and obj.constraints:
                for constraint in obj.constraints:
                    if constraint.name in initial_obj['constraints']:
                        initial_const = initial_obj['constraints'][constraint.name]
                        
                        for prop, initial_val in initial_const.items():
                            current_val = self.safe_get_attr(constraint, prop)
                            if current_val is not None and not self.values_equal(current_val, initial_val):
                                return f'bpy.data.objects["{obj.name}"].constraints["{constraint.name}"].{prop}'
            
            # Pose bones
            if 'pose_bones' in initial_obj and obj.type == 'ARMATURE' and obj.pose:
                for pose_bone in obj.pose.bones:
                    if pose_bone.name in initial_obj['pose_bones']:
                        initial_pose_bone = initial_obj['pose_bones'][pose_bone.name]
                        
                        # Transform properties
                        transform_props = ['location', 'rotation_euler', 'rotation_quaternion', 'scale',
                                         'lock_location', 'lock_rotation', 'lock_scale']
                        for prop in transform_props:
                            if prop in initial_pose_bone:
                                current_val = getattr(pose_bone, prop)
                                if not self.values_equal(current_val, initial_pose_bone[prop]):
                                    # Check for array index
                                    if hasattr(current_val, '__len__') and not isinstance(current_val, str):
                                        for i, (curr, init) in enumerate(zip(current_val, initial_pose_bone[prop])):
                                            if not self.values_equal(curr, init):
                                                return f'bpy.data.objects["{obj.name}"].pose.bones["{pose_bone.name}"].{prop}[{i}]'
                                    return f'bpy.data.objects["{obj.name}"].pose.bones["{pose_bone.name}"].{prop}'
                        
                        # Constraints
                        if 'constraints' in initial_pose_bone and pose_bone.constraints:
                            for constraint in pose_bone.constraints:
                                if constraint.name in initial_pose_bone['constraints']:
                                    initial_const = initial_pose_bone['constraints'][constraint.name]
                                    
                                    for prop, initial_val in initial_const.items():
                                        current_val = self.safe_get_attr(constraint, prop)
                                        if current_val is not None and not self.values_equal(current_val, initial_val):
                                            return f'bpy.data.objects["{obj.name}"].pose.bones["{pose_bone.name}"].constraints["{constraint.name}"].{prop}'
            
            # Shape keys
            if 'shape_keys' in initial_obj and obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
                for key_block in obj.data.shape_keys.key_blocks:
                    if key_block.name in initial_obj['shape_keys']:
                        initial_key = initial_obj['shape_keys'][key_block.name]
                        
                        for prop, initial_val in initial_key.items():
                            current_val = getattr(key_block, prop)
                            if not self.values_equal(current_val, initial_val):
                                return f'bpy.data.objects["{obj.name}"].data.shape_keys.key_blocks["{key_block.name}"].{prop}'
            
            # Modifiers
            if 'modifiers' in initial_obj and obj.modifiers:
                for modifier in obj.modifiers:
                    if modifier.name in initial_obj['modifiers']:
                        initial_mod = initial_obj['modifiers'][modifier.name]
                        
                        for prop, initial_val in initial_mod.items():
                            current_val = self.safe_get_attr(modifier, prop)
                            if current_val is not None and not self.values_equal(current_val, initial_val):
                                return f'bpy.data.objects["{obj.name}"].modifiers["{modifier.name}"].{prop}'
            
            # Custom properties
            if 'custom_props' in initial_obj:
                for key, initial_val in initial_obj['custom_props'].items():
                    if key in obj and not self.ignore(key):
                        current_val = obj[key]
                        if not self.values_equal(current_val, initial_val):
                            if self.is_valid_editable_path(f'bpy.data.objects["{obj.name}"]["{key}"]'):
                                return f'bpy.data.objects["{obj.name}"]["{key}"]'

        
        # Check cameras
        for camera in bpy.data.cameras:
            cam_key = f"cameras.{camera.name}"
            if cam_key not in self._initial_state:
                continue
                
            initial_cam = self._initial_state[cam_key]
            
            # Basic camera properties
            cam_props = ['lens', 'sensor_width', 'sensor_height', 'clip_start', 'clip_end', 
                        'type', 'ortho_scale', 'shift_x', 'shift_y']
            for prop in cam_props:
                if prop in initial_cam:
                    current_val = getattr(camera, prop)
                    if not self.values_equal(current_val, initial_cam[prop]):
                        return f'bpy.data.cameras["{camera.name}"].{prop}'
            
            # DOF properties
            if 'dof' in initial_cam and hasattr(camera, 'dof'):
                for prop, initial_val in initial_cam['dof'].items():
                    current_val = self.safe_get_attr(camera.dof, prop)
                    if current_val is not None and not self.values_equal(current_val, initial_val):
                        return f'bpy.data.cameras["{camera.name}"].dof.{prop}'
            
            # Custom properties
            if 'custom_props' in initial_cam:
                for key, initial_val in initial_cam['custom_props'].items():
                    if key in camera and not self.ignore(key):
                        current_val = camera[key]
                        if not self.values_equal(current_val, initial_val):
                            return f'bpy.data.cameras["{camera.name}"]["{key}"]'

        # Check lights
        for light in bpy.data.lights:
            light_key = f"lights.{light.name}"
            if light_key not in self._initial_state:
                continue
                
            initial_light = self._initial_state[light_key]
            
            # Basic light properties
            light_props = ['type', 'energy', 'color', 'use_shadow', 'shadow_soft_size', 
                          'cutoff_distance', 'use_custom_distance', 'angle', 'spot_size', 
                          'spot_blend', 'size', 'size_y', 'shape']
            for prop in light_props:
                if prop in initial_light:
                    current_val = getattr(light, prop)
                    if not self.values_equal(current_val, initial_light[prop]):
                        # Check for array index (like color)
                        if hasattr(current_val, '__len__') and not isinstance(current_val, str):
                            for i, (curr, init) in enumerate(zip(current_val, initial_light[prop])):
                                if not self.values_equal(curr, init):
                                    return f'bpy.data.lights["{light.name}"].{prop}[{i}]'
                        return f'bpy.data.lights["{light.name}"].{prop}'
            
            # Custom properties
            if 'custom_props' in initial_light:
                for key, initial_val in initial_light['custom_props'].items():
                    if key in light and not self.ignore(key):
                        current_val = light[key]
                        if not self.values_equal(current_val, initial_val):
                            return f'bpy.data.lights["{light.name}"]["{key}"]'

        
        # Check armatures
        for armature in bpy.data.armatures:
            arm_key = f"armatures.{armature.name}"
            if arm_key not in self._initial_state:
                continue
                
            initial_arm = self._initial_state[arm_key]
            
            # Armature display properties
            arm_props = ['show_bone_custom_shapes', 'show_names', 'show_axes', 'display_type']
            for prop in arm_props:
                if prop in initial_arm:
                    current_val = self.safe_get_attr(armature, prop)
                    if current_val is not None and current_val != initial_arm[prop]:
                        return f'bpy.data.armatures["{armature.name}"].{prop}'
            
            # Bone collections visibility
            if 'collections' in initial_arm:
                for collection_name, initial_collection in initial_arm['collections'].items():
                    attr_name = initial_collection.get('attr_name', 'collections_all')
                    
                    if hasattr(armature, attr_name):
                        try:
                            collections = getattr(armature, attr_name)
                            for collection in collections:
                                if collection.name == collection_name:
                                    if collection.is_visible != initial_collection['is_visible']:
                                        return f'bpy.data.armatures["{armature.name}"].{attr_name}["{collection_name}"].is_visible'
                                    break
                        except:
                            pass
            
            # Bone properties
            if 'bones' in initial_arm:
                for bone in armature.bones:
                    if bone.name in initial_arm['bones']:
                        initial_bone = initial_arm['bones'][bone.name]
                        
                        for prop, initial_val in initial_bone.items():
                            current_val = self.safe_get_attr(bone, prop)
                            if current_val is not None and not self.values_equal(current_val, initial_val):
                                return f'bpy.data.armatures["{armature.name}"].bones["{bone.name}"].{prop}'
            
            # Custom properties
            if 'custom_props' in initial_arm:
                for key, initial_val in initial_arm['custom_props'].items():
                    if key in armature and not self.ignore(key):
                        current_val = armature[key]
                        if not self.values_equal(current_val, initial_val):
                            return f'bpy.data.armatures["{armature.name}"]["{key}"]'

        
        # Check materials
        for mat in bpy.data.materials:
            mat_key = f"materials.{mat.name}"
            if mat_key not in self._initial_state:
                continue
                
            initial_mat = self._initial_state[mat_key]
            
            # Basic material properties
            for prop, initial_val in initial_mat.items():
                if prop in ['nodes', 'custom_props']:
                    continue
                    
                current_val = self.safe_get_attr(mat, prop)
                if current_val is not None and current_val != initial_val:
                    return f'bpy.data.materials["{mat.name}"].{prop}'
            
            # Node tree
            if 'nodes' in initial_mat and mat.use_nodes and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.name in initial_mat['nodes']:
                        initial_node = initial_mat['nodes'][node.name]
                        
                        # Node properties
                        for prop, initial_val in initial_node.items():
                            if prop in ['inputs', 'outputs', 'color_ramp']:
                                continue
                                
                            current_val = self.safe_get_attr(node, prop)
                            if current_val is not None and not self.values_equal(current_val, initial_val):
                                return f'bpy.data.materials["{mat.name}"].node_tree.nodes["{node.name}"].{prop}'
                        
                        # Input values
                        if 'inputs' in initial_node and hasattr(node, 'inputs'):
                            for i, input_socket in enumerate(node.inputs):
                                if i in initial_node['inputs'] and hasattr(input_socket, 'default_value'):
                                    try:
                                        current_val = input_socket.default_value
                                        initial_val = initial_node['inputs'][i]
                                        
                                        if not self.values_equal(current_val, initial_val):
                                            # Check for array index (like color or vector inputs)
                                            if hasattr(current_val, '__len__') and not isinstance(current_val, str):
                                                for j, (curr, init) in enumerate(zip(current_val, initial_val)):
                                                    if not self.values_equal(curr, init):
                                                        return f'bpy.data.materials["{mat.name}"].node_tree.nodes["{node.name}"].inputs[{i}].default_value[{j}]'
                                            return f'bpy.data.materials["{mat.name}"].node_tree.nodes["{node.name}"].inputs[{i}].default_value'
                                    except:
                                        pass
                        
                        # Output values
                        if 'outputs' in initial_node and hasattr(node, 'outputs'):
                            for i, output_socket in enumerate(node.outputs):
                                if i in initial_node['outputs'] and hasattr(output_socket, 'default_value'):
                                    try:
                                        current_val = output_socket.default_value
                                        initial_val = initial_node['outputs'][i]
                                        
                                        if not self.values_equal(current_val, initial_val):
                                            # Check for array index
                                            if hasattr(current_val, '__len__') and not isinstance(current_val, str):
                                                for j, (curr, init) in enumerate(zip(current_val, initial_val)):
                                                    if not self.values_equal(curr, init):
                                                        return f'bpy.data.materials["{mat.name}"].node_tree.nodes["{node.name}"].outputs[{i}].default_value[{j}]'
                                            return f'bpy.data.materials["{mat.name}"].node_tree.nodes["{node.name}"].outputs[{i}].default_value'
                                    except:
                                        pass
                        
                        # ColorRamp elements
                        if 'color_ramp' in initial_node and hasattr(node, 'color_ramp') and node.color_ramp:
                            if 'elements' in initial_node['color_ramp']:
                                try:
                                    for i, element in enumerate(node.color_ramp.elements):
                                        if i in initial_node['color_ramp']['elements']:
                                            initial_element = initial_node['color_ramp']['elements'][i]
                                            
                                            # Position
                                            if 'position' in initial_element:
                                                if not self.values_equal(element.position, initial_element['position']):
                                                    return f'bpy.data.materials["{mat.name}"].node_tree.nodes["{node.name}"].color_ramp.elements[{i}].position'
                                            
                                            # Color
                                            if 'color' in initial_element:
                                                if not self.values_equal(element.color, initial_element['color']):
                                                    # Check individual color components
                                                    for j, (curr, init) in enumerate(zip(element.color, initial_element['color'])):
                                                        if not self.values_equal(curr, init):
                                                            return f'bpy.data.materials["{mat.name}"].node_tree.nodes["{node.name}"].color_ramp.elements[{i}].color[{j}]'
                                                    return f'bpy.data.materials["{mat.name}"].node_tree.nodes["{node.name}"].color_ramp.elements[{i}].color'
                                except:
                                    pass
            
            # Custom properties
            if 'custom_props' in initial_mat:
                for key, initial_val in initial_mat['custom_props'].items():
                    if key in mat and not self.ignore(key):
                        current_val = mat[key]
                        if not self.values_equal(current_val, initial_val):
                            return f'bpy.data.materials["{mat.name}"]["{key}"]'

        
        # Check scenes
        for scene in bpy.data.scenes:
            scene_key = f"scenes.{scene.name}"
            if scene_key not in self._initial_state:
                continue
                
            initial_scene = self._initial_state[scene_key]
            
            # Basic scene properties
            basic_props = ['frame_current', 'frame_start', 'frame_end', 'frame_step', 'use_gravity']
            for prop in basic_props:
                if prop in initial_scene:
                    current_val = getattr(scene, prop)
                    if not self.values_equal(current_val, initial_scene[prop]):
                        return f'bpy.data.scenes["{scene.name}"].{prop}'
            
            # Gravity vector
            if 'gravity' in initial_scene:
                if not self.values_equal(scene.gravity, initial_scene['gravity']):
                    # Check individual components
                    for i, (current, initial) in enumerate(zip(scene.gravity, initial_scene['gravity'])):
                        if not self.values_equal(current, initial):
                            return f'bpy.data.scenes["{scene.name}"].gravity[{i}]'
            
            # Render properties
            if 'render' in initial_scene and hasattr(scene, 'render'):
                for prop, initial_val in initial_scene['render'].items():
                    current_val = self.safe_get_attr(scene.render, prop)
                    if current_val is not None and not self.values_equal(current_val, initial_val):
                        return f'bpy.data.scenes["{scene.name}"].render.{prop}'
            
            # EEVEE properties
            if 'eevee' in initial_scene and hasattr(scene, 'eevee'):
                for prop, initial_val in initial_scene['eevee'].items():
                    current_val = self.safe_get_attr(scene.eevee, prop)
                    if current_val is not None and not self.values_equal(current_val, initial_val):
                        return f'bpy.data.scenes["{scene.name}"].eevee.{prop}'
            
            # Cycles properties
            if 'cycles' in initial_scene and hasattr(scene, 'cycles'):
                for prop, initial_val in initial_scene['cycles'].items():
                    current_val = self.safe_get_attr(scene.cycles, prop)
                    if current_val is not None and not self.values_equal(current_val, initial_val):
                        return f'bpy.data.scenes["{scene.name}"].cycles.{prop}'
            
            # World properties
            if 'world' in initial_scene and scene.world:
                world_props = ['use_nodes', 'color']
                for prop in world_props:
                    if prop in initial_scene['world']:
                        current_val = getattr(scene.world, prop)
                        if not self.values_equal(current_val, initial_scene['world'][prop]):
                            # Check for array index (like color)
                            if hasattr(current_val, '__len__') and not isinstance(current_val, str):
                                for i, (curr, init) in enumerate(zip(current_val, initial_scene['world'][prop])):
                                    if not self.values_equal(curr, init):
                                        return f'bpy.data.worlds["{scene.world.name}"].{prop}[{i}]'
                            return f'bpy.data.worlds["{scene.world.name}"].{prop}'
                
                # World node tree
                if 'nodes' in initial_scene['world'] and scene.world.use_nodes and scene.world.node_tree:
                    for node in scene.world.node_tree.nodes:
                        if node.name in initial_scene['world']['nodes']:
                            initial_node = initial_scene['world']['nodes'][node.name]
                            
                            # Input values
                            if 'inputs' in initial_node and hasattr(node, 'inputs'):
                                for i, input_socket in enumerate(node.inputs):
                                    if i in initial_node['inputs'] and hasattr(input_socket, 'default_value'):
                                        try:
                                            current_val = input_socket.default_value
                                            initial_val = initial_node['inputs'][i]
                                            
                                            if not self.values_equal(current_val, initial_val):
                                                # Check for array index
                                                if hasattr(current_val, '__len__') and not isinstance(current_val, str):
                                                    for j, (curr, init) in enumerate(zip(current_val, initial_val)):
                                                        if not self.values_equal(curr, init):
                                                            return f'bpy.data.worlds["{scene.world.name}"].node_tree.nodes["{node.name}"].inputs[{i}].default_value[{j}]'
                                                return f'bpy.data.worlds["{scene.world.name}"].node_tree.nodes["{node.name}"].inputs[{i}].default_value'
                                        except:
                                            pass
        
        return None


class SCENE_OT_add_path_target(bpy.types.Operator):
    bl_idname = "scene.add_path_target"
    bl_label = "Add Path"
    bl_description = "Add the custom path to the target list"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.custom_path_input:
            self.report({'ERROR'}, "Please enter a custom path")
            return {'CANCELLED'}
        
        # Parse the path to get data block, data path, and index
        data_block, data_path, index = parse_target_path(props.custom_path_input)
        
        if data_block is None or data_path is None:
            self.report({'ERROR'}, "Invalid or unsupported path format")
            return {'CANCELLED'}
        
        # Auto-detect the property type using the parsed components
        detected_type = auto_detect_path_type(data_block, data_path, index)
        
        path_data = get_path_list_data(props)
        
        # Create unique key for this path
        key = props.custom_path_input
        
        # Check if already exists
        if key in path_data:
            self.report({'WARNING'}, f"Path already exists in list")
            return {'CANCELLED'}
        
        # Store type but use the same min/max values for both float and boolean
        path_data[key] = {
            'path': props.custom_path_input,
            'type': detected_type,
            'min_value': props.path_min_value,
            'max_value': props.path_max_value
        }
        
        set_path_list_data(props, path_data)
        
        # Clear inputs after adding
        props.custom_path_input = ""
        props.path_min_value = 0.0
        props.path_max_value = 1.0
        props.path_false_value = 0.0
        props.path_true_value = 1.0
        props.path_recorded_min = False
        props.path_recorded_max = False
        
        # Report what was detected and added
        type_text = "boolean" if detected_type == 'BOOLEAN' else "float"
        self.report({'INFO'}, f"Added {type_text} path")
        
        return {'FINISHED'}


class SCENE_OT_record_path_min(bpy.types.Operator):
    """Record current value of custom path as minimum"""
    bl_idname = "scene.record_path_min"
    bl_label = "Record Min"
    bl_description = "Record the current value of the custom path as minimum"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.custom_path_input:
            self.report({'ERROR'}, "Please enter a custom path first")
            return {'CANCELLED'}
        
        try:
            # Parse and get current value
            data_block, data_path, index = parse_target_path(props.custom_path_input)
            
            if data_block is None or data_path is None:
                self.report({'ERROR'}, "Invalid path format")
                return {'CANCELLED'}
            
            # Get current value
            if index >= 0:
                current_value = data_block.path_resolve(data_path)[index]
            else:
                current_value = data_block.path_resolve(data_path)
            
            # Detect type for info message
            detected_type = auto_detect_path_type(data_block, data_path, index)
            
            # Always record as min value, regardless of type
            props.path_min_value = float(current_value)
            props.path_recorded_min = True
            
            type_text = "BOOLEAN" if detected_type == 'BOOLEAN' else "FLOAT"
            self.report({'INFO'}, f"Recorded MIN value: {current_value:.3f} ({type_text})")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read path: {str(e)}")
            return {'CANCELLED'}


class SCENE_OT_record_path_max(bpy.types.Operator):
    """Record current value of custom path as maximum"""
    bl_idname = "scene.record_path_max"
    bl_label = "Record Max"
    bl_description = "Record the current value of the custom path as maximum"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.custom_path_input:
            self.report({'ERROR'}, "Please enter a custom path first")
            return {'CANCELLED'}
        
        try:
            # Parse and get current value
            data_block, data_path, index = parse_target_path(props.custom_path_input)
            
            if data_block is None or data_path is None:
                self.report({'ERROR'}, "Invalid path format")
                return {'CANCELLED'}
            
            # Get current value
            if index >= 0:
                current_value = data_block.path_resolve(data_path)[index]
            else:
                current_value = data_block.path_resolve(data_path)
            
            # Detect type for info message
            detected_type = auto_detect_path_type(data_block, data_path, index)
            
            # Always record as max value, regardless of type
            props.path_max_value = float(current_value)
            props.path_recorded_max = True
            
            type_text = "BOOLEAN" if detected_type == 'BOOLEAN' else "FLOAT"
            self.report({'INFO'}, f"Recorded MAX value: {current_value:.3f} ({type_text})")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read path: {str(e)}")
            return {'CANCELLED'}


class SCENE_OT_record_source_path_min(bpy.types.Operator):
    """Record current value of the custom path source as minimum"""
    bl_idname = "scene.record_source_path_min"
    bl_label = "Record Min"
    bl_description = "Record the current value of the custom path as minimum"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props

        if not props.source_custom_path_input:
            self.report({'ERROR'}, "Please enter a custom path first")
            return {'CANCELLED'}

        try:
            data_block, data_path, index = parse_target_path(props.source_custom_path_input)

            if data_block is None or data_path is None:
                self.report({'ERROR'}, "Invalid path format")
                return {'CANCELLED'}

            if index >= 0:
                current_value = data_block.path_resolve(data_path)[index]
            else:
                current_value = data_block.path_resolve(data_path)

            detected_type = auto_detect_path_type(data_block, data_path, index)

            props.source_path_min_value = float(current_value)
            props.source_path_recorded_min = True

            type_text = "BOOLEAN" if detected_type == 'BOOLEAN' else "FLOAT"
            self.report({'INFO'}, f"Recorded MIN value: {current_value:.3f} ({type_text})")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to read path: {str(e)}")
            return {'CANCELLED'}


class SCENE_OT_record_source_path_max(bpy.types.Operator):
    """Record current value of the custom path source as maximum"""
    bl_idname = "scene.record_source_path_max"
    bl_label = "Record Max"
    bl_description = "Record the current value of the custom path as maximum"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props

        if not props.source_custom_path_input:
            self.report({'ERROR'}, "Please enter a custom path first")
            return {'CANCELLED'}

        try:
            data_block, data_path, index = parse_target_path(props.source_custom_path_input)

            if data_block is None or data_path is None:
                self.report({'ERROR'}, "Invalid path format")
                return {'CANCELLED'}

            if index >= 0:
                current_value = data_block.path_resolve(data_path)[index]
            else:
                current_value = data_block.path_resolve(data_path)

            detected_type = auto_detect_path_type(data_block, data_path, index)

            props.source_path_max_value = float(current_value)
            props.source_path_recorded_max = True

            type_text = "BOOLEAN" if detected_type == 'BOOLEAN' else "FLOAT"
            self.report({'INFO'}, f"Recorded MAX value: {current_value:.3f} ({type_text})")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to read path: {str(e)}")
            return {'CANCELLED'}


class ANIM_OT_setup_custom_path_source(bpy.types.Operator):
    """Register the custom path as the driver source"""
    bl_idname = "anim.setup_custom_path_source"
    bl_label = "Set as Source"
    bl_description = "Register this custom path as the driver source"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props

        path_str = props.source_custom_path_input.strip()
        if not path_str:
            self.report({'ERROR'}, "Please enter or eyedrop a path first")
            return {'CANCELLED'}

        config = parse_custom_path_source(path_str)
        if not config:
            self.report({'ERROR'}, "Could not resolve this path")
            return {'CANCELLED'}

        if props.source_path_min_value == props.source_path_max_value:
            self.report({'ERROR'}, "Min and Max can't be equal")
            return {'CANCELLED'}

        # Clear other source types so this one takes priority
        props.from_armature              = ""
        props.from_bone                  = ""
        props.from_has_min               = False
        props.from_has_max               = False
        props.from_detected_axis         = ""
        props.from_object                = ""
        props.from_object_has_min        = False
        props.from_object_has_max        = False
        props.from_object_detected_axis  = ""
        props.custom_prop_is_set         = False
        props.custom_prop_source_object  = None
        props.custom_prop_bone           = ""
        props.shapekey_src_is_set        = False
        props.shapekey_src_object        = None
        props.shapekey_src_name          = ""

        props.source_custom_path_is_set = True
        self.report({'INFO'}, f"Custom path source set: {path_str}")
        return {'FINISHED'}


class ANIM_OT_clear_custom_path_source(bpy.types.Operator):
    """Clear the custom path source"""
    bl_idname = "anim.clear_custom_path_source"
    bl_label = "Clear Custom Path Source"
    bl_description = "Clear the custom path source configuration"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        props.source_custom_path_is_set   = False
        props.source_custom_path_input    = ""
        props.source_path_recorded_min    = False
        props.source_path_recorded_max    = False
        props.source_path_min_value       = 0.0
        props.source_path_max_value       = 1.0
        self.report({'INFO'}, "Custom path source cleared")
        return {'FINISHED'}


class SCENE_OT_edit_path_target(bpy.types.Operator):
    bl_idname = "scene.edit_path_target"
    bl_label = "Edit Path"
    bl_description = "Edit this path (loads values into inputs and removes from list)"
    
    key_to_edit: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        path_data = get_path_list_data(props)
        
        if self.key_to_edit not in path_data:
            self.report({'ERROR'}, "Path not found in list")
            return {'CANCELLED'}
        
        # Get the data
        path_info = path_data[self.key_to_edit]
        
        # Load values into inputs - same for both float and boolean
        props.custom_path_input = path_info['path']
        props.path_min_value = path_info['min_value']
        props.path_max_value = path_info['max_value']
        
        # Reset other values
        props.path_false_value = 0.0
        props.path_true_value = 1.0
        props.path_recorded_min = False
        props.path_recorded_max = False
        
        # Remove from list
        del path_data[self.key_to_edit]
        set_path_list_data(props, path_data)
        
        type_text = "boolean" if path_info['type'] == 'BOOLEAN' else "float"
        self.report({'INFO'}, f"Loaded {type_text} path for editing")
        return {'FINISHED'}


class SCENE_OT_remove_path_target(bpy.types.Operator):
    bl_idname = "scene.remove_path_target"
    bl_label = "Remove"
    bl_description = "Remove this path from the list"
   
    key_to_remove: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        path_data = get_path_list_data(props)
        
        if self.key_to_remove in path_data:
            path_info = path_data[self.key_to_remove]
            del path_data[self.key_to_remove]
            set_path_list_data(props, path_data)
            
            # Show shortened path in message
            display_path = self.key_to_remove if len(self.key_to_remove) <= 40 else self.key_to_remove[:37] + "..."
            self.report({'INFO'}, f"Removed path: {display_path}")
        else:
            self.report({'ERROR'}, "Path not found in list")
        
        return {'FINISHED'}

#---------------------------------------
# Actions>Driver&Expression Operators
#---------------------------------------
class ANIM_OT_create_drivers(bpy.types.Operator):
    bl_idname = "anim.create_drivers"
    bl_label = "Create Drivers"
    bl_description = "Create drivers from FROM source to all targets"
    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Initialize variables
        from_path = None
        source_name = None
        from_min = None
        from_max = None

        # ── Multi-source blend takes priority if enabled and configured ────
        use_multi_source = False
        multi_slots = [
            {'label': s.label, 'kind': s.kind, 'from_path': s.from_path,
             'from_min': s.from_min, 'from_max': s.from_max, 'source_name': s.source_name}
            for s in context.scene.multi_source_slots
        ]
        if props.multi_source_enabled:
            if len(multi_slots) < 2:
                self.report({'ERROR'}, "Multi-Source needs at least 2 added sources")
                return {'CANCELLED'}
            if props.multi_source_combine_mode == 'DISTANCE' and len(multi_slots) != 2:
                self.report({'ERROR'}, "Distance combine mode needs exactly 2 sources")
                return {'CANCELLED'}
            if props.multi_source_from_min == props.multi_source_from_max:
                self.report({'ERROR'}, "Combined source Min and Max can't be equal")
                return {'CANCELLED'}
            use_multi_source = True

        source_space = 'WORLD_SPACE' if (props.ui_complexity != 'BASIC' and props.source_use_world_space) else 'LOCAL_SPACE'

        if not use_multi_source:
            # Determine source - check what's actually configured
            # Priority: Check if we have valid recorded data first
            if props.from_bone and props.from_has_min and props.from_has_max and props.from_detected_axis:
                # Using bone source - verify it still exists
                armature = bpy.data.objects.get(props.from_armature)
                if not armature or props.from_bone not in armature.pose.bones:
                    self.report({'ERROR'}, f"Source bone '{props.from_bone}' not found in armature '{props.from_armature}'")
                    return {'CANCELLED'}
            
                # Get FROM bone values
                from_axis_type, from_axis_name = props.from_detected_axis.split(' ')
                from_axis_index = ['X', 'Y', 'Z'].index(from_axis_name)
            
                if from_axis_type == 'LOC':
                    from_min = props.from_min_location[from_axis_index]
                    from_max = props.from_max_location[from_axis_index]
                    from_prop = 'location'
                elif from_axis_type == 'ROT':
                    from_min = props.from_min_rotation[from_axis_index]
                    from_max = props.from_max_rotation[from_axis_index]
                    from_prop = 'rotation_euler'
                elif from_axis_type == 'SCALE':
                    from_min = props.from_min_scale[from_axis_index]
                    from_max = props.from_max_scale[from_axis_index]
                    from_prop = 'scale'
            
                from_path = f"{props.from_armature}.pose.bones[\"{props.from_bone}\"].{from_prop}[{from_axis_index}]"
                source_name = props.from_armature
            
            elif props.from_object and props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis:
                # Using object source - verify it still exists
                obj = bpy.data.objects.get(props.from_object)
                if not obj:
                    self.report({'ERROR'}, f"Source object '{props.from_object}' not found")
                    return {'CANCELLED'}
            
                # Get FROM object values
                from_axis_type, from_axis_name = props.from_object_detected_axis.split(' ')
                from_axis_index = ['X', 'Y', 'Z'].index(from_axis_name)
            
                if from_axis_type == 'LOC':
                    from_min = props.from_object_min_location[from_axis_index]
                    from_max = props.from_object_max_location[from_axis_index]
                    from_prop = 'location'
                elif from_axis_type == 'ROT':
                    from_min = props.from_object_min_rotation[from_axis_index]
                    from_max = props.from_object_max_rotation[from_axis_index]
                    from_prop = 'rotation_euler'
                elif from_axis_type == 'SCALE':
                    from_min = props.from_object_min_scale[from_axis_index]
                    from_max = props.from_object_max_scale[from_axis_index]
                    from_prop = 'scale'
            
                from_path = f"{props.from_object}.{from_prop}[{from_axis_index}]"
                source_name = props.from_object
            
            elif props.custom_prop_is_set and props.custom_prop_source_object:
                # Custom property source
                obj    = props.custom_prop_source_object
                pname  = props.custom_prop_name.strip()
                bname  = props.custom_prop_bone.strip()
                from_min   = props.custom_prop_min
                from_max   = props.custom_prop_max
                source_name = obj.name

                if bname:
                    # Bone custom property
                    if obj.type != 'ARMATURE' or bname not in obj.pose.bones:
                        self.report({'ERROR'}, f"Bone '{bname}' not found in armature '{obj.name}'")
                        return {'CANCELLED'}
                    if pname not in obj.pose.bones[bname]:
                        self.report({'ERROR'}, f"Custom property '{pname}' not found on bone '{bname}'")
                        return {'CANCELLED'}
                    from_path = f'{obj.name}.pose.bones["{bname}"]["{pname}"]'
                else:
                    # Object custom property
                    if pname not in obj:
                        self.report({'ERROR'}, f"Custom property '{pname}' not found on object '{obj.name}'")
                        return {'CANCELLED'}
                    from_path = f'{obj.name}["{pname}"]'

            elif props.shapekey_src_is_set and props.shapekey_src_object:
                # Shape key value source
                obj = props.shapekey_src_object
                key_name = props.shapekey_src_name.strip()

                if not (obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys):
                    self.report({'ERROR'}, f"'{obj.name}' has no shape keys")
                    return {'CANCELLED'}
                if key_name not in obj.data.shape_keys.key_blocks:
                    self.report({'ERROR'}, f"Shape key '{key_name}' not found on '{obj.name}'")
                    return {'CANCELLED'}

                from_min = props.shapekey_src_min
                from_max = props.shapekey_src_max
                source_name = obj.name
                from_path = f'{obj.name}.data.shape_keys.key_blocks["{key_name}"].value'

            else:
                self.report({'ERROR'}, "No source configured. Please record MIN/MAX or set up a custom property source.")
                return {'CANCELLED'}
        
            # Validate that we have all required source data
            if not all([from_path, source_name, from_min is not None, from_max is not None]):
                self.report({'ERROR'}, "Failed to configure source data")
                return {'CANCELLED'}
        
        # Rest of the method remains the same...
        drivers_created = 0
        
        if props.target_type == 'CUSTOM_POSE':
            # Create drivers for custom pose bones.
            # Keys are "ArmatureName::BoneName"; bone_data['bone_name'] holds
            # the bare bone name, bone_data['armature'] the armature name.
            to_data = get_to_bones_data(props)
            if not to_data:
                self.report({'ERROR'}, "No TO bones recorded")
                return {'CANCELLED'}

            for key, bone_data in to_data.items():
                if not (bone_data.get('has_min', False) and bone_data.get('has_max', False)):
                    print(f"Skipping {key}: missing min/max data")
                    continue

                detected_changes = bone_data.get('detected_changes', [])
                if not detected_changes:
                    print(f"Skipping {key}: no detected changes")
                    continue

                is_object_entry = bone_data.get('is_object', False)
                actual_bone_name = bone_data.get('bone_name') or key.split('::')[-1]
                armature_name    = bone_data.get('armature')
                object_name      = bone_data.get('object')

                for change in detected_changes:
                    try:
                        to_prop = change.get('type')
                        to_axis = change.get('axis')
                        to_min  = change.get('min_val')
                        to_max  = change.get('max_val')

                        if is_object_entry:
                            if None in [to_prop, to_axis, to_min, to_max, object_name]:
                                print(f"Skipping change for {key}: missing data")
                                continue
                        else:
                            if None in [to_prop, to_axis, to_min, to_max, armature_name]:
                                print(f"Skipping change for {key}: missing data")
                                continue

                        if props.invert_target_range:
                            to_min, to_max = to_max, to_min

                        if is_object_entry:
                            to_path = f"{object_name}.{to_prop}[{to_axis}]"
                        else:
                            to_path = f"{armature_name}.pose.bones[\"{actual_bone_name}\"].{to_prop}[{to_axis}]"

                        print(f"Creating driver: {key} -> {to_prop}[{to_axis}]")

                        if use_multi_source:
                            success = createMultiSourceDriver(
                                slots=multi_slots,
                                combine_mode=props.multi_source_combine_mode,
                                fromMin=props.multi_source_from_min,
                                fromMax=props.multi_source_from_max,
                                to_path=to_path,
                                toMin=to_min,
                                toMax=to_max,
                                isDegrees=False,
                                curve_type=props.driver_curve_type,
                                source_space=source_space
                            )
                        else:
                            success = createDriver(
                                armature_name=source_name,
                                from_path=from_path,
                                fromMin=from_min,
                                fromMax=from_max,
                                to_path=to_path,
                                toMin=to_min,
                                toMax=to_max,
                                selfRotation=False,
                                isDegrees=False,
                                curve_type=props.driver_curve_type,
                                source_space=source_space
                            )

                        if success:
                            drivers_created += 1
                            print(f"✓ Driver created for {key}")
                        else:
                            print(f"✗ Driver creation failed for {key}")

                    except Exception as e:
                        print(f"Error processing change for {key}: {e}")
                        continue

        elif props.target_type == 'SHAPEKEY_LIST':
            shapekey_data = get_shapekey_list_data(props)
            if not shapekey_data:
                self.report({'ERROR'}, "No shape keys in list")
                return {'CANCELLED'}

            for key, sk_data in shapekey_data.items():
                try:
                    if use_multi_source:
                        # Multi-source blend applies globally - skip the
                        # per-entry single-source rebuild entirely.
                        sk_from_path = sk_from_min = sk_from_max = sk_source_name = None
                    else:
                        # Prefer the explicit source_type snapshotted at add-time -
                        # this is unambiguous, unlike guessing from string fields
                        # that may be empty for one source type but stale/left over
                        # from a previously-configured one.
                        entry_source_type = sk_data.get('source_type', '')

                        if not entry_source_type:
                            # Backward compatibility with entries saved before
                            # source_type existed: fall back to the old heuristic.
                            if sk_data.get('source_bone') and sk_data.get('source_armature'):
                                entry_source_type = 'BONE'
                            elif sk_data.get('source_object'):
                                entry_source_type = 'OBJECT'
                            elif props.custom_prop_is_set and props.custom_prop_source_object:
                                entry_source_type = 'CUSTOM_PROP'
                            elif props.from_bone and props.from_armature:
                                entry_source_type = 'BONE'
                            elif props.from_object:
                                entry_source_type = 'OBJECT'

                        entry_armature = sk_data.get('source_armature') or props.from_armature
                        entry_bone     = sk_data.get('source_bone')     or props.from_bone
                        entry_object   = sk_data.get('source_object')   or props.from_object

                        if entry_source_type == 'CUSTOM_PROP':
                            cp_obj_name = sk_data.get('source_custom_prop_object') or (
                            props.custom_prop_source_object.name if props.custom_prop_source_object else '')
                            cp_bone_name = sk_data.get('source_custom_prop_bone', '') or props.custom_prop_bone
                            cp_prop_name = (sk_data.get('source_custom_prop_name') or props.custom_prop_name).strip()
                            sk_from_min = sk_data.get('source_custom_prop_min', props.custom_prop_min)
                            sk_from_max = sk_data.get('source_custom_prop_max', props.custom_prop_max)

                            cp_obj = bpy.data.objects.get(cp_obj_name)
                            if not cp_obj:
                                print(f"Skipping {key}: custom property source object '{cp_obj_name}' not found")
                                continue

                            if cp_bone_name:
                                if cp_obj.type != 'ARMATURE' or cp_bone_name not in cp_obj.pose.bones:
                                    print(f"Skipping {key}: bone '{cp_bone_name}' not found in armature '{cp_obj.name}'")
                                    continue
                                if cp_prop_name not in cp_obj.pose.bones[cp_bone_name]:
                                    print(f"Skipping {key}: custom property '{cp_prop_name}' not found on bone '{cp_bone_name}'")
                                    continue
                                sk_from_path = f'{cp_obj.name}.pose.bones["{cp_bone_name}"]["{cp_prop_name}"]'
                            else:
                                if cp_prop_name not in cp_obj:
                                    print(f"Skipping {key}: custom property '{cp_prop_name}' not found on object '{cp_obj.name}'")
                                    continue
                                sk_from_path = f'{cp_obj.name}["{cp_prop_name}"]'

                            sk_source_name = cp_obj.name

                        elif entry_source_type == 'SHAPEKEY':
                            sko_name = sk_data.get('source_shapekey_object') or (
                                props.shapekey_src_object.name if props.shapekey_src_object else '')
                            sk_key_name = (sk_data.get('source_shapekey_name') or props.shapekey_src_name).strip()
                            sk_from_min = sk_data.get('source_shapekey_min', props.shapekey_src_min)
                            sk_from_max = sk_data.get('source_shapekey_max', props.shapekey_src_max)

                            sko_obj = bpy.data.objects.get(sko_name)
                            if not sko_obj:
                                print(f"Skipping {key}: shape key source object '{sko_name}' not found")
                                continue
                            if not (sko_obj.data and hasattr(sko_obj.data, 'shape_keys') and sko_obj.data.shape_keys):
                                print(f"Skipping {key}: '{sko_obj.name}' has no shape keys")
                                continue
                            if sk_key_name not in sko_obj.data.shape_keys.key_blocks:
                                print(f"Skipping {key}: shape key '{sk_key_name}' not found on '{sko_obj.name}'")
                                continue

                            sk_from_path = f'{sko_obj.name}.data.shape_keys.key_blocks["{sk_key_name}"].value'
                            sk_source_name = sko_obj.name

                        # Rebuild from_path and from_min/max from the entry's own snapshot
                        elif entry_bone and entry_armature:
                            detected = sk_data.get('from_detected_axis') or props.from_detected_axis
                            ax_type, ax_name = detected.split(' ')
                            ax_idx = ['X', 'Y', 'Z'].index(ax_name)
                            if ax_type == 'LOC':
                                sk_from_min = sk_data.get('from_min_location', list(props.from_min_location))[ax_idx]
                                sk_from_max = sk_data.get('from_max_location', list(props.from_max_location))[ax_idx]
                                sk_prop = 'location'
                            elif ax_type == 'ROT':
                                sk_from_min = sk_data.get('from_min_rotation', list(props.from_min_rotation))[ax_idx]
                                sk_from_max = sk_data.get('from_max_rotation', list(props.from_max_rotation))[ax_idx]
                                sk_prop = 'rotation_euler'
                            else:  # SCALE
                                sk_from_min = sk_data.get('from_min_scale', list(props.from_min_scale))[ax_idx]
                                sk_from_max = sk_data.get('from_max_scale', list(props.from_max_scale))[ax_idx]
                                sk_prop = 'scale'
                            sk_from_path = f"{entry_armature}.pose.bones[\"{entry_bone}\"].{sk_prop}[{ax_idx}]"
                            sk_source_name = entry_armature

                        elif entry_object:
                            detected = sk_data.get('from_object_detected_axis') or props.from_object_detected_axis
                            ax_type, ax_name = detected.split(' ')
                            ax_idx = ['X', 'Y', 'Z'].index(ax_name)
                            if ax_type == 'LOC':
                                sk_from_min = sk_data.get('from_object_min_location', list(props.from_object_min_location))[ax_idx]
                                sk_from_max = sk_data.get('from_object_max_location', list(props.from_object_max_location))[ax_idx]
                                sk_prop = 'location'
                            elif ax_type == 'ROT':
                                sk_from_min = sk_data.get('from_object_min_rotation', list(props.from_object_min_rotation))[ax_idx]
                                sk_from_max = sk_data.get('from_object_max_rotation', list(props.from_object_max_rotation))[ax_idx]
                                sk_prop = 'rotation_euler'
                            else:
                                sk_from_min = sk_data.get('from_object_min_scale', list(props.from_object_min_scale))[ax_idx]
                                sk_from_max = sk_data.get('from_object_max_scale', list(props.from_object_max_scale))[ax_idx]
                                sk_prop = 'scale'
                            sk_from_path = f"{entry_object}.{sk_prop}[{ax_idx}]"
                            sk_source_name = entry_object

                        else:
                            # No per-entry source: fall back to global (old behaviour)
                            sk_from_path  = from_path
                            sk_from_min   = from_min
                            sk_from_max   = from_max
                            sk_source_name = source_name

                    to_path = f"{sk_data['object']}.data.shape_keys.key_blocks[\"{sk_data['shapekey']}\"].value"

                    sk_to_min = sk_data['min_value']
                    sk_to_max = sk_data['max_value']
                    if props.invert_target_range:
                        sk_to_min, sk_to_max = sk_to_max, sk_to_min

                    if use_multi_source:
                        success = createMultiSourceDriver(
                            slots=multi_slots,
                            combine_mode=props.multi_source_combine_mode,
                            fromMin=props.multi_source_from_min,
                            fromMax=props.multi_source_from_max,
                            to_path=to_path,
                            toMin=sk_to_min,
                            toMax=sk_to_max,
                            isDegrees=False,
                            curve_type=props.driver_curve_type,
                            source_space=source_space
                        )
                    else:
                        success = createDriver(
                            armature_name=sk_source_name,
                            from_path=sk_from_path,
                            fromMin=sk_from_min,
                            fromMax=sk_from_max,
                            to_path=to_path,
                            toMin=sk_to_min,
                            toMax=sk_to_max,
                            selfRotation=False,
                            isDegrees=False,
                            curve_type=props.driver_curve_type,
                            source_space=source_space
                        )

                    if success:
                        drivers_created += 1

                except Exception as e:
                    print(f"Error creating shapekey driver for {key}: {e}")
                    continue



        elif props.target_type == 'PATH_LIST':
            # Create drivers for custom paths
            path_data = get_path_list_data(props)
            if not path_data:
                self.report({'ERROR'}, "No custom paths in list")
                return {'CANCELLED'}
            
            for path, path_info in path_data.items():
                try:
                    # Use min_value and max_value for both FLOAT and BOOLEAN types
                    to_min = path_info['min_value']
                    to_max = path_info['max_value']

                    if props.invert_target_range:
                        to_min, to_max = to_max, to_min

                    if use_multi_source:
                        success = createMultiSourceDriver(
                            slots=multi_slots,
                            combine_mode=props.multi_source_combine_mode,
                            fromMin=props.multi_source_from_min,
                            fromMax=props.multi_source_from_max,
                            to_path=path,
                            toMin=to_min,
                            toMax=to_max,
                            isDegrees=False,
                            curve_type=props.driver_curve_type,
                            source_space=source_space
                        )
                    else:
                        success = createDriver(
                            armature_name=source_name,
                            from_path=from_path,
                            fromMin=from_min,
                            fromMax=from_max,
                            to_path=path,
                            toMin=to_min,
                            toMax=to_max,
                            selfRotation=False,
                            isDegrees=False,
                            curve_type=props.driver_curve_type,
                            source_space=source_space
                        )
                    
                    if success:
                        drivers_created += 1
                        
                except Exception as e:
                    print(f"Error creating path driver for {path}: {e}")
                    continue
        
        self.report({'INFO'}, f"Created {drivers_created} drivers")
        return {'FINISHED'}


class ANIM_OT_remove_drivers(bpy.types.Operator):
    bl_idname = "anim.remove_drivers"
    bl_label = "Remove Drivers"
    bl_description = "Remove drivers from configured targets only"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Validate we have a source configured
        source_configured = False
        if props.from_bone and props.from_armature:
            source_configured = True
        elif props.from_object:
            source_configured = True
        
        if not source_configured:
            self.report({'ERROR'}, "No source configured")
            return {'CANCELLED'}
        
        drivers_removed = 0
        
        # Remove drivers from configured targets only
        if props.target_type == 'CUSTOM_POSE':
            to_data = get_to_bones_data(props)

            for key, bone_data in to_data.items():
                if bone_data.get('is_object'):
                    obj = bpy.data.objects.get(bone_data.get('object', ''))
                    if not obj or not obj.animation_data:
                        continue

                    for change in bone_data.get('detected_changes', []):
                        to_prop = change['type']
                        to_axis = change['axis']

                        try:
                            obj.driver_remove(to_prop, to_axis)
                            drivers_removed += 1
                            print(f"✓ Removed driver: {obj.name}.{to_prop}[{to_axis}]")
                        except Exception as e:
                            print(f"Driver not found or already removed: {to_prop}[{to_axis}]")
                    continue

                armature = bpy.data.objects.get(bone_data.get('armature', ''))
                if not armature or not armature.animation_data:
                    continue

                actual_bone_name = bone_data.get('bone_name') or key.split('::')[-1]

                for change in bone_data.get('detected_changes', []):
                    to_prop = change['type']
                    to_axis = change['axis']
                    data_path = f'pose.bones["{actual_bone_name}"].{to_prop}'

                    try:
                        armature.driver_remove(data_path, to_axis)
                        drivers_removed += 1
                        print(f"✓ Removed driver: {armature.name}.{data_path}[{to_axis}]")
                    except Exception as e:
                        print(f"Driver not found or already removed: {data_path}[{to_axis}]")
        
        elif props.target_type == 'SHAPEKEY_LIST':
            shapekey_data = get_shapekey_list_data(props)
            
            for key, sk_data in shapekey_data.items():
                obj = bpy.data.objects.get(sk_data['object'])
                if not obj or not obj.data or not hasattr(obj.data, 'shape_keys'):
                    continue
                
                data_path = f'key_blocks["{sk_data["shapekey"]}"].value'
                
                try:
                    obj.data.shape_keys.driver_remove(data_path)
                    drivers_removed += 1
                    print(f"✓ Removed shapekey driver: {obj.name}.{data_path}")
                except Exception as e:
                    print(f"Shapekey driver not found or already removed: {data_path}")
        
        elif props.target_type == 'PATH_LIST':
            path_data = get_path_list_data(props)
            
            for path, path_info in path_data.items():
                # Parse the custom path to get object and data path
                data_block, data_path, index = parse_target_path(path)
                
                if data_block and data_path:
                    try:
                        if index >= 0:
                            data_block.driver_remove(data_path, index)
                        else:
                            data_block.driver_remove(data_path)
                        drivers_removed += 1
                        print(f"✓ Removed custom path driver: {path}")
                    except Exception as e:
                        print(f"Custom path driver not found or already removed: {path}")
        
        if drivers_removed > 0:
            self.report({'INFO'}, f"Removed {drivers_removed} drivers from configured targets")
        else:
            self.report({'WARNING'}, "No drivers were removed (may not exist or already removed)")
        
        return {'FINISHED'}
class ANIM_OT_mirror_source(bpy.types.Operator):
    """Mirror source bone/object to opposite side"""
    bl_idname = "anim.mirror_source"
    bl_label = "Mirror Source"
    bl_description = "Mirror source to opposite side (keeps recorded min/max values)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        try:
            success, message = mirror_source(props)
            
            if success:
                self.report({'INFO'}, message)
            else:
                self.report({'WARNING'}, message)
                
        except Exception as e:
            self.report({'ERROR'}, f"Mirror failed: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

class ANIM_OT_mirror_targets(bpy.types.Operator):
    """Mirror target configuration to opposite side"""
    bl_idname = "anim.mirror_targets"
    bl_label = "Mirror Targets"
    bl_description = "Mirror all targets to opposite side"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        try:
            if props.target_type == 'CUSTOM_POSE':
                success, message = mirror_pose_targets(props)
            elif props.target_type == 'SHAPEKEY_LIST':
                success, message = mirror_shapekey_targets(props)
            elif props.target_type == 'PATH_LIST':
                self.report({'INFO'}, "Mirror not supported for custom paths")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Unknown target type")
                return {'CANCELLED'}
            
            if success:
                self.report({'INFO'}, message)
            else:
                self.report({'WARNING'}, message)
                
        except Exception as e:
            self.report({'ERROR'}, f"Mirror failed: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}



class SCENE_OT_clear_all(bpy.types.Operator):
    bl_idname = "scene.clear_all"
    bl_label = "Clear All"
    bl_description = "Clear all recorded data"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Clear bone data
        props.from_armature = ""
        props.from_bone = ""
        props.from_has_min = False
        props.from_has_max = False
        props.from_detected_axis = ""
        
        # Clear object data
        props.from_object = ""
        props.from_object_has_min = False
        props.from_object_has_max = False
        props.from_object_detected_axis = ""
        
        # Clear target data
        props.to_bones_data = "{}"
        props.shapekey_list_data = "{}"
        props.path_list_data = "{}"
        props.shapekey_target_object = ""
        props.shapekey_name = ""
        props.custom_path_input = ""

        # Clear custom property source
        props.custom_prop_is_set        = False
        props.custom_prop_source_object = None
        props.custom_prop_bone          = ""
        props.custom_prop_name          = "my_driver"
        props.custom_prop_min           = 0.0
        props.custom_prop_max           = 1.0

        # Clear shape-key source
        props.shapekey_src_is_set = False
        props.shapekey_src_object = None
        props.shapekey_src_name   = ""
        props.shapekey_src_min    = 0.0
        props.shapekey_src_max    = 1.0

        # Clear custom path source
        props.source_custom_path_is_set   = False
        props.source_custom_path_input    = ""
        props.source_path_recorded_min    = False
        props.source_path_recorded_max    = False
        props.source_path_min_value       = 0.0
        props.source_path_max_value       = 1.0

        # Clear multi-source blend
        props.multi_source_enabled = False
        context.scene.multi_source_slots.clear()
        context.scene.multi_source_slot_index = 0
        props.multi_source_from_min = 0.0
        props.multi_source_from_max = 1.0
        
        self.report({'INFO'}, "All data cleared")
        return {'FINISHED'}

class SCENE_OT_set_target_type(bpy.types.Operator):
    bl_idname = "scene.set_target_type"
    bl_label = "Set Target Type"
    bl_description = "Set the target type"
  
    target_type: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        props.target_type = self.target_type
        return {'FINISHED'}


class SCENE_OT_set_source_mode(bpy.types.Operator):
    """Switch the source panel between transform recording and custom property mode"""
    bl_idname = "scene.set_source_mode"
    bl_label = "Set Source Mode"
    bl_description = "Switch between bone/object transform source and custom property source"

    mode: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        if self.mode == 'CUSTOM_PROP':
            props.from_source_type = 'CUSTOM_PROP'
        elif self.mode == 'SHAPEKEY':
            props.from_source_type = 'SHAPEKEY'
        else:
            # Restore to whichever transform type was last used
            # (keep existing from_source_type if it is BONE or OBJECT)
            if props.from_source_type in ('CUSTOM_PROP', 'SHAPEKEY'):
                props.from_source_type = 'BONE'
        return {'FINISHED'}

class SCENE_OT_clear_source(bpy.types.Operator):
    """Clear all source configuration"""
    bl_idname = "scene.clear_source"
    bl_label = "Clear Source"
    bl_options = {'REGISTER', 'UNDO'}
  
    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Clear bone source data
        props.from_bone = ""
        props.from_has_min = False
        props.from_has_max = False
        props.from_detected_axis = ""
        props.from_min_rotation = (0.0, 0.0, 0.0)
        props.from_max_rotation = (0.0, 0.0, 0.0)
        props.from_min_location = (0.0, 0.0, 0.0)
        props.from_max_location = (0.0, 0.0, 0.0)
        props.from_min_scale = (1.0, 1.0, 1.0)
        props.from_max_scale = (1.0, 1.0, 1.0)
        
        # Clear object source data
        props.from_object = ""
        props.from_object_has_min = False
        props.from_object_has_max = False
        props.from_object_detected_axis = ""
        props.from_object_min_rotation = (0.0, 0.0, 0.0)
        props.from_object_max_rotation = (0.0, 0.0, 0.0)
        props.from_object_min_location = (0.0, 0.0, 0.0)
        props.from_object_max_location = (0.0, 0.0, 0.0)
        props.from_object_min_scale = (1.0, 1.0, 1.0)
        props.from_object_max_scale = (1.0, 1.0, 1.0)

        # Clear custom property source
        props.custom_prop_is_set        = False
        props.custom_prop_source_object = None
        props.custom_prop_bone          = ""
        props.custom_prop_name          = "my_driver"
        props.custom_prop_min           = 0.0
        props.custom_prop_max           = 1.0

        # Clear shape-key source
        props.shapekey_src_is_set   = False
        props.shapekey_src_object   = None
        props.shapekey_src_name     = ""
        props.shapekey_src_min      = 0.0
        props.shapekey_src_max      = 1.0

        # Clear custom path source
        props.source_custom_path_is_set   = False
        props.source_custom_path_input    = ""
        props.source_path_recorded_min    = False
        props.source_path_recorded_max    = False
        props.source_path_min_value       = 0.0
        props.source_path_max_value       = 1.0
        
        self.report({'INFO'}, "Source configuration cleared")
        return {'FINISHED'}

class SCENE_OT_clear_targets(bpy.types.Operator):
    """Clear all target configuration"""
    bl_idname = "scene.clear_targets"
    bl_label = "Clear Targets"
    bl_options = {'REGISTER', 'UNDO'}
  
    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Clear pose targets
        props.to_bones_data = ""
        
        # Clear shapekey targets
        props.shapekey_list_data = ""
        props.shapekey_target_object = ""
        props.shapekey_name = ""
        props.shapekey_min_value = 0.0
        props.shapekey_max_value = 1.0
        
        # Clear path targets
        props.path_list_data = ""
        props.custom_path_input = ""
        props.path_min_value = 0.0
        props.path_max_value = 1.0
        props.path_false_value = 0.0
        props.path_true_value = 1.0
        
        self.report({'INFO'}, "Target configuration cleared")
        return {'FINISHED'}


#---------------------------------------
# Custom Property Source Operator
#---------------------------------------
class ANIM_OT_setup_custom_prop_source(bpy.types.Operator):
    """Create (or reuse) a custom property and register it as the driver source"""
    bl_idname = "anim.setup_custom_prop_source"
    bl_label = "Set as Source"
    bl_description = "Create the custom property if needed and register it as the driver source"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props

        obj = props.custom_prop_source_object
        if not obj:
            self.report({'ERROR'}, "Please select an object or armature")
            return {'CANCELLED'}

        prop_name = props.custom_prop_name.strip()
        if not prop_name:
            self.report({'ERROR'}, "Please enter a property name")
            return {'CANCELLED'}

        bone_name = props.custom_prop_bone.strip()
        prop_min  = props.custom_prop_min
        prop_max  = props.custom_prop_max

        if prop_min >= prop_max:
            self.report({'ERROR'}, "Min must be less than Max")
            return {'CANCELLED'}

        # ── Create or update the custom property ──────────────────────────
        if bone_name:
            # Bone custom property
            if obj.type != 'ARMATURE':
                self.report({'ERROR'}, "Selected object is not an armature")
                return {'CANCELLED'}
            if bone_name not in obj.pose.bones:
                self.report({'ERROR'}, f"Bone '{bone_name}' not found in armature '{obj.name}'")
                return {'CANCELLED'}
            target = obj.pose.bones[bone_name]
            container_name = f"{obj.name} > {bone_name}"
        else:
            target = obj
            container_name = obj.name

        # Create the property if it doesn't exist; always (re)set its UI range
        if prop_name not in target:
            target[prop_name] = (prop_min + prop_max) / 2.0
            self.report({'INFO'}, f"Created custom property '{prop_name}' on {container_name}")
        else:
            self.report({'INFO'}, f"Using existing custom property '{prop_name}' on {container_name}")

        # Apply ui_data for soft min/max (Blender 3.0+ / 4.x / 5.x compatible)
        try:
            ui = target.id_properties_ui(prop_name)
            ui.update(min=prop_min, max=prop_max, soft_min=prop_min, soft_max=prop_max)
        except Exception as e:
            print(f"WARNING: Could not set UI data for custom property: {e}")

        # ── Clear existing bone/object source so custom prop takes priority ──
        props.from_armature              = ""
        props.from_bone                  = ""
        props.from_has_min               = False
        props.from_has_max               = False
        props.from_detected_axis         = ""
        props.from_object                = ""
        props.from_object_has_min        = False
        props.from_object_has_max        = False
        props.from_object_detected_axis  = ""

        # Clear shape-key source too, so only one source is ever active
        props.shapekey_src_is_set = False
        props.shapekey_src_object = None
        props.shapekey_src_name   = ""

        # Clear custom path source too
        props.source_custom_path_is_set = False
        props.source_custom_path_input  = ""

        # Mark as configured
        props.custom_prop_is_set = True

        return {'FINISHED'}


class ANIM_OT_setup_shapekey_source(bpy.types.Operator):
    """Register a shape key's value as the driver source"""
    bl_idname = "anim.setup_shapekey_source"
    bl_label = "Set as Source"
    bl_description = "Register the selected shape key's value as the driver source"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props

        obj = props.shapekey_src_object
        if not obj:
            self.report({'ERROR'}, "Please select an object")
            return {'CANCELLED'}

        if not (obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys):
            self.report({'ERROR'}, f"'{obj.name}' has no shape keys")
            return {'CANCELLED'}

        key_name = props.shapekey_src_name.strip()
        if not key_name:
            self.report({'ERROR'}, "Please choose a shape key")
            return {'CANCELLED'}

        if key_name not in obj.data.shape_keys.key_blocks:
            self.report({'ERROR'}, f"Shape key '{key_name}' not found on '{obj.name}'")
            return {'CANCELLED'}

        if props.shapekey_src_min >= props.shapekey_src_max:
            self.report({'ERROR'}, "Min must be less than Max")
            return {'CANCELLED'}

        # ── Clear existing bone/object/custom-prop source so this takes priority ──
        props.from_armature              = ""
        props.from_bone                  = ""
        props.from_has_min               = False
        props.from_has_max               = False
        props.from_detected_axis         = ""
        props.from_object                = ""
        props.from_object_has_min        = False
        props.from_object_has_max        = False
        props.from_object_detected_axis  = ""
        props.custom_prop_is_set         = False
        props.custom_prop_source_object  = None
        props.custom_prop_bone           = ""

        # Clear custom path source too
        props.source_custom_path_is_set = False
        props.source_custom_path_input  = ""

        props.shapekey_src_is_set = True

        return {'FINISHED'}


class ANIM_OT_clear_shapekey_source(bpy.types.Operator):
    """Clear the shape-key source"""
    bl_idname = "anim.clear_shapekey_source"
    bl_label = "Clear Shape Key Source"
    bl_description = "Clear the shape-key source configuration"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        props.shapekey_src_is_set = False
        props.shapekey_src_object = None
        props.shapekey_src_name   = ""
        props.shapekey_src_min    = 0.0
        props.shapekey_src_max    = 1.0
        self.report({'INFO'}, "Shape key source cleared")
        return {'FINISHED'}


class ANIM_OT_edit_shapekey_source(bpy.types.Operator):
    """Fine-tune the active shape-key source's Min/Max via popup (More tier and up)"""
    bl_idname = "anim.edit_shapekey_source"
    bl_label = "Edit Shape Key Source"
    bl_description = "Fine-tune this shape key source's recorded Min/Max values"
    bl_options = {'REGISTER', 'UNDO'}

    edit_min: bpy.props.FloatProperty(name="Min")
    edit_max: bpy.props.FloatProperty(name="Max")

    def invoke(self, context, event):
        props = context.scene.driver_recorder_props
        if not props.shapekey_src_is_set:
            self.report({'ERROR'}, "No shape key source configured")
            return {'CANCELLED'}
        self.edit_min = props.shapekey_src_min
        self.edit_max = props.shapekey_src_max
        return context.window_manager.invoke_props_dialog(self, width=250)

    def draw(self, context):
        props = context.scene.driver_recorder_props
        layout = self.layout
        obj = props.shapekey_src_object
        layout.label(text=f"{obj.name if obj else '?'} \u203a {props.shapekey_src_name}", icon='SHAPEKEY_DATA')
        row = layout.row(align=True)
        row.prop(self, "edit_min")
        row.prop(self, "edit_max")

    def execute(self, context):
        props = context.scene.driver_recorder_props
        if self.edit_min == self.edit_max:
            self.report({'ERROR'}, "Min and Max can't be equal")
            return {'CANCELLED'}
        props.shapekey_src_min = self.edit_min
        props.shapekey_src_max = self.edit_max
        self.report({'INFO'}, "Shape key source updated")
        return {'FINISHED'}


class ANIM_OT_clear_custom_prop_source(bpy.types.Operator):
    """Clear the custom property source"""
    bl_idname = "anim.clear_custom_prop_source"
    bl_label = "Clear Custom Prop Source"
    bl_description = "Clear the custom property source configuration"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        props.custom_prop_is_set         = False
        props.custom_prop_source_object  = None
        props.custom_prop_bone           = ""
        props.custom_prop_name           = "my_driver"
        props.custom_prop_min            = 0.0
        props.custom_prop_max            = 1.0
        self.report({'INFO'}, "Custom property source cleared")
        return {'FINISHED'}


#---------------------------------------
# Custom Property Browser
#---------------------------------------
class CustomPropBrowserItem(bpy.types.PropertyGroup):
    """One row in the Custom Property Browser list."""
    prop_name: bpy.props.StringProperty()
    type_label: bpy.props.StringProperty()
    value_display: bpy.props.StringProperty()


class ANIM_OT_refresh_custom_prop_browser(bpy.types.Operator):
    """Refresh the list of custom properties on the selected object/bone"""
    bl_idname = "anim.refresh_custom_prop_browser"
    bl_label = "Refresh"
    bl_description = "Rescan the selected object/bone for custom properties"
    bl_options = {'REGISTER'}

    def execute(self, context):
        _refresh_cp_browse_list(context)
        self.report({'INFO'}, f"Found {len(context.scene.cp_browse_list)} custom propert(y/ies)")
        return {'FINISHED'}


class ANIM_OT_add_custom_prop_entry(bpy.types.Operator):
    """Create a new Toggle/Integer/Float custom property on the selected object/bone"""
    bl_idname = "anim.add_custom_prop_entry"
    bl_label = "Add Custom Property"
    bl_description = "Create a new custom property on the selected object/bone"
    bl_options = {'REGISTER', 'UNDO'}

    new_prop_name: bpy.props.StringProperty(name="Name", default="my_property")
    new_prop_type: bpy.props.EnumProperty(
        name="Type",
        items=[
            ('BOOL', 'Toggle', 'A True/False on-off value'),
            ('INT', 'Integer', 'A whole number'),
            ('FLOAT', 'Float', 'A decimal number'),
        ],
        default='FLOAT'
    )
    new_bool_value: bpy.props.BoolProperty(name="Value", default=False)
    new_int_value: bpy.props.IntProperty(name="Value", default=0)
    new_float_value: bpy.props.FloatProperty(name="Value", default=0.0)
    new_min: bpy.props.FloatProperty(name="Min", default=0.0)
    new_max: bpy.props.FloatProperty(name="Max", default=1.0)

    def invoke(self, context, event):
        props = context.scene.driver_recorder_props
        if not props.custom_prop_source_object:
            self.report({'ERROR'}, "Please select an object or armature first")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "new_prop_name")
        layout.prop(self, "new_prop_type", expand=True)

        if self.new_prop_type == 'BOOL':
            layout.prop(self, "new_bool_value")
        else:
            row = layout.row(align=True)
            if self.new_prop_type == 'INT':
                row.prop(self, "new_int_value")
            else:
                row.prop(self, "new_float_value")
            range_row = layout.row(align=True)
            range_row.prop(self, "new_min")
            range_row.prop(self, "new_max")

    def execute(self, context):
        props = context.scene.driver_recorder_props
        target = _cp_browse_target(props)
        if target is None:
            self.report({'ERROR'}, "Please select an object or armature first")
            return {'CANCELLED'}

        name = self.new_prop_name.strip()
        if not name:
            self.report({'ERROR'}, "Please enter a property name")
            return {'CANCELLED'}

        if self.new_prop_type in ('INT', 'FLOAT') and self.new_min >= self.new_max:
            self.report({'ERROR'}, "Min must be less than Max")
            return {'CANCELLED'}

        if self.new_prop_type == 'BOOL':
            target[name] = self.new_bool_value
        elif self.new_prop_type == 'INT':
            target[name] = self.new_int_value
        else:
            target[name] = self.new_float_value

        if self.new_prop_type in ('INT', 'FLOAT'):
            try:
                ui = target.id_properties_ui(name)
                ui.update(min=self.new_min, max=self.new_max, soft_min=self.new_min, soft_max=self.new_max)
            except Exception as e:
                print(f"WARNING: Could not set UI data for new custom property: {e}")

        _refresh_cp_browse_list(context)
        self.report({'INFO'}, f"Created custom property '{name}'")
        return {'FINISHED'}


class ANIM_OT_remove_custom_prop_entry(bpy.types.Operator):
    """Delete the selected custom property from the object/bone entirely"""
    bl_idname = "anim.remove_custom_prop_entry"
    bl_label = "Remove Custom Property"
    bl_description = "Delete the selected custom property from the object/bone (this cannot be undone by clearing the source - it removes the actual property)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.driver_recorder_props
        browse_list = scene.cp_browse_list
        index = scene.cp_browse_index

        if not (0 <= index < len(browse_list)):
            self.report({'ERROR'}, "No property selected")
            return {'CANCELLED'}

        prop_name = browse_list[index].prop_name
        target = _cp_browse_target(props)
        if target is None:
            self.report({'ERROR'}, "Target object/bone not found")
            return {'CANCELLED'}

        if prop_name in target:
            del target[prop_name]
            self.report({'INFO'}, f"Removed custom property '{prop_name}'")
        else:
            self.report({'WARNING'}, f"Property '{prop_name}' not found (already removed?)")

        _refresh_cp_browse_list(context)
        return {'FINISHED'}


class ANIM_OT_record_custom_prop_min(bpy.types.Operator):
    """Record the property's current live value as Min (Advanced only)"""
    bl_idname = "anim.record_custom_prop_min"
    bl_label = "Record Min"
    bl_description = "Read the selected property's current value and use it as Min"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        target = _cp_browse_target(props)
        prop_name = props.custom_prop_name.strip()
        if target is None or not prop_name or prop_name not in target:
            self.report({'ERROR'}, "Select an existing property first")
            return {'CANCELLED'}

        props.custom_prop_min = float(target[prop_name])
        self.report({'INFO'}, f"Recorded Min = {props.custom_prop_min:.3g}")
        return {'FINISHED'}


class ANIM_OT_record_custom_prop_max(bpy.types.Operator):
    """Record the property's current live value as Max (Advanced only)"""
    bl_idname = "anim.record_custom_prop_max"
    bl_label = "Record Max"
    bl_description = "Read the selected property's current value and use it as Max"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        target = _cp_browse_target(props)
        prop_name = props.custom_prop_name.strip()
        if target is None or not prop_name or prop_name not in target:
            self.report({'ERROR'}, "Select an existing property first")
            return {'CANCELLED'}

        props.custom_prop_max = float(target[prop_name])
        self.report({'INFO'}, f"Recorded Max = {props.custom_prop_max:.3g}")
        return {'FINISHED'}

#---------------------------------------
# Multi-Source (Advanced)
#---------------------------------------
class MultiSourceSlotItem(bpy.types.PropertyGroup):
    """One row in the Multi-Source blend list - a real CollectionProperty
    (not a JSON blob), so it can use the same native list widget
    (template_list) as the Driver Review and Custom Property Browser lists."""
    label: bpy.props.StringProperty()
    kind: bpy.props.StringProperty()
    from_path: bpy.props.StringProperty()
    from_min: bpy.props.FloatProperty()
    from_max: bpy.props.FloatProperty()
    source_name: bpy.props.StringProperty()


def _describe_active_source_for_label(props):
    """Short human-readable label for whatever source is currently active -
    used only for the Multi-Source slot list display."""
    if props.from_bone and props.from_has_min and props.from_has_max and props.from_detected_axis:
        return f"{props.from_armature} \u203a {props.from_bone} ({props.from_detected_axis})"
    elif props.from_object and props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis:
        return f"{props.from_object} ({props.from_object_detected_axis})"
    elif props.custom_prop_is_set and props.custom_prop_source_object:
        obj = props.custom_prop_source_object
        pname = props.custom_prop_name.strip()
        bname = props.custom_prop_bone.strip()
        return f'{obj.name}{"." + bname if bname else ""}["{pname}"]'
    elif props.shapekey_src_is_set and props.shapekey_src_object:
        return f"{props.shapekey_src_object.name} \u203a {props.shapekey_src_name}"
    elif props.source_custom_path_is_set and props.source_custom_path_input:
        return props.source_custom_path_input
    return "Unknown source"


def _detect_active_source_kind(props):
    """Which source kind is currently active - used to pick an icon for the
    Multi-Source slot list ('BONE_OBJECT', 'CUSTOM_PROP', 'SHAPEKEY',
    'CUSTOM_PATH', or None if nothing valid is configured)."""
    if props.from_bone and props.from_has_min and props.from_has_max and props.from_detected_axis:
        return 'BONE_OBJECT'
    elif props.from_object and props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis:
        return 'BONE_OBJECT'
    elif props.custom_prop_is_set and props.custom_prop_source_object:
        return 'CUSTOM_PROP'
    elif props.shapekey_src_is_set and props.shapekey_src_object:
        return 'SHAPEKEY'
    elif props.source_custom_path_is_set and props.source_custom_path_input:
        return 'CUSTOM_PATH'
    return None


class ANIM_OT_add_multi_source_slot(bpy.types.Operator):
    """Add the currently configured source as one slot in the multi-source blend"""
    bl_idname = "anim.add_multi_source_slot"
    bl_label = "Add Source"
    bl_description = "Add the currently configured source (above) as one input to the multi-source blend, then clear it so you can set up the next one"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props

        from_path, from_min, from_max, source_name, error = resolve_active_single_source(props)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        slots = context.scene.multi_source_slots
        item = slots.add()
        item.from_path = from_path
        item.from_min = from_min
        item.from_max = from_max
        item.source_name = source_name
        item.label = _describe_active_source_for_label(props)
        item.kind = _detect_active_source_kind(props) or ''
        context.scene.multi_source_slot_index = len(slots) - 1

        # Clear the active source so the user can configure the next slot
        bpy.ops.scene.clear_source()

        self.report({'INFO'}, f"Added source slot ({len(slots)} total)")
        return {'FINISHED'}


class ANIM_OT_remove_multi_source_slot(bpy.types.Operator):
    """Remove the selected slot from the multi-source blend"""
    bl_idname = "anim.remove_multi_source_slot"
    bl_label = "Remove Source Slot"
    bl_description = "Remove the selected source from the blend"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        slots = scene.multi_source_slots
        index = scene.multi_source_slot_index
        if not (0 <= index < len(slots)):
            self.report({'ERROR'}, "No source selected")
            return {'CANCELLED'}
        slots.remove(index)
        scene.multi_source_slot_index = min(index, len(slots) - 1)
        return {'FINISHED'}


class ANIM_OT_edit_multi_source_slot(bpy.types.Operator):
    """Fine-tune the selected multi-source slot's recorded Min/Max in a small popup"""
    bl_idname = "anim.edit_multi_source_slot"
    bl_label = "Edit Source Slot"
    bl_description = "Fine-tune the selected source's recorded Min/Max values"
    bl_options = {'REGISTER', 'UNDO'}

    edit_min: bpy.props.FloatProperty(name="Min")
    edit_max: bpy.props.FloatProperty(name="Max")

    def invoke(self, context, event):
        scene = context.scene
        slots = scene.multi_source_slots
        index = scene.multi_source_slot_index
        if not (0 <= index < len(slots)):
            self.report({'ERROR'}, "No source selected")
            return {'CANCELLED'}

        self.edit_min = slots[index].from_min
        self.edit_max = slots[index].from_max
        return context.window_manager.invoke_props_dialog(self, width=250)

    def draw(self, context):
        scene = context.scene
        slots = scene.multi_source_slots
        index = scene.multi_source_slot_index
        layout = self.layout
        if 0 <= index < len(slots):
            layout.label(text=slots[index].label or 'Source', icon='MOD_ARRAY')
        row = layout.row(align=True)
        row.prop(self, "edit_min")
        row.prop(self, "edit_max")

    def execute(self, context):
        scene = context.scene
        slots = scene.multi_source_slots
        index = scene.multi_source_slot_index
        if not (0 <= index < len(slots)):
            return {'CANCELLED'}

        if self.edit_min == self.edit_max:
            self.report({'ERROR'}, "Min and Max can't be equal")
            return {'CANCELLED'}

        slots[index].from_min = self.edit_min
        slots[index].from_max = self.edit_max
        self.report({'INFO'}, "Source slot updated")
        return {'FINISHED'}


class ANIM_OT_move_multi_source_slot(bpy.types.Operator):
    """Move the selected multi-source slot up or down - order matters for Subtract and Distance"""
    bl_idname = "anim.move_multi_source_slot"
    bl_label = "Move Source Slot"
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.StringProperty(default='UP')  # 'UP' or 'DOWN'

    def execute(self, context):
        scene = context.scene
        slots = scene.multi_source_slots
        i = scene.multi_source_slot_index
        j = i - 1 if self.direction == 'UP' else i + 1
        if 0 <= i < len(slots) and 0 <= j < len(slots):
            slots.move(i, j)
            scene.multi_source_slot_index = j
        return {'FINISHED'}


class ANIM_OT_clear_multi_source(bpy.types.Operator):
    """Clear all multi-source slots"""
    bl_idname = "anim.clear_multi_source"
    bl_label = "Clear All Sources"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.multi_source_slots.clear()
        context.scene.multi_source_slot_index = 0
        self.report({'INFO'}, "Multi-source slots cleared")
        return {'FINISHED'}


#---------------------------------------
# Driver Review
#---------------------------------------
class EZDriverReviewItem(bpy.types.PropertyGroup):
    """One row in the Driver Review list - a single driver Easy Driver created."""
    id_name: bpy.props.StringProperty()
    id_type: bpy.props.StringProperty()
    data_path: bpy.props.StringProperty()
    array_index: bpy.props.IntProperty(default=-1)
    curve_type: bpy.props.StringProperty()
    source_desc: bpy.props.StringProperty()
    target_desc: bpy.props.StringProperty()
    expression: bpy.props.StringProperty()
    expr_valid: bpy.props.BoolProperty(default=True)
    source_valid: bpy.props.BoolProperty(default=True)


def _populate_review_list(context, results):
    review_list = context.scene.ez_driver_review_list
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
    context.scene.ez_driver_review_index = 0


class ANIM_OT_scan_easydriver_drivers(bpy.types.Operator):
    """Scan the file for drivers created by Easy Driver and refresh the review list"""
    bl_idname = "anim.scan_easydriver_drivers"
    bl_label = "Scan Drivers"
    bl_description = "Scan the current file for every driver Easy Driver has created, and check whether each one still works"
    bl_options = {'REGISTER'}

    def execute(self, context):
        results = scan_easydriver_drivers()
        _populate_review_list(context, results)
        self.report({'INFO'}, f"Found {len(results)} Easy Driver driver(s)")
        return {'FINISHED'}


class ANIM_OT_edit_driver_expression(bpy.types.Operator):
    """Directly edit a driver's raw Python expression (Advanced only) - for
    when you need something the curve-type dropdown can't produce"""
    bl_idname = "anim.edit_driver_expression"
    bl_label = "Edit Expression"
    bl_description = "Edit this driver's raw expression directly"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty()
    new_expression: bpy.props.StringProperty(name="Expression")

    def invoke(self, context, event):
        review_list = context.scene.ez_driver_review_list
        if not (0 <= self.index < len(review_list)):
            self.report({'ERROR'}, "Driver not found - try Scan again")
            return {'CANCELLED'}

        item = review_list[self.index]
        id_block = resolve_easydriver_id_block(item.id_name, item.id_type)
        fcurve = find_driver_fcurve(id_block, item.data_path, item.array_index) if id_block else None

        # Prefer the live expression straight off the fcurve if we can find
        # it (most current), otherwise fall back to what was last scanned.
        self.new_expression = fcurve.driver.expression if fcurve else item.expression
        return context.window_manager.invoke_props_dialog(self, width=450)

    def draw(self, context):
        review_list = context.scene.ez_driver_review_list
        layout = self.layout
        if 0 <= self.index < len(review_list):
            layout.label(text=review_list[self.index].target_desc, icon='DRIVER')
        layout.prop(self, "new_expression", text="")
        warn = layout.row()
        warn.scale_y = 0.8
        warn.label(text="Raw Python expression - invalid syntax will be rejected", icon='INFO')

    def execute(self, context):
        review_list = context.scene.ez_driver_review_list
        if not (0 <= self.index < len(review_list)):
            return {'CANCELLED'}

        item = review_list[self.index]

        # Validate before touching anything - reject broken syntax outright
        try:
            compile(self.new_expression, "<driver>", "eval")
        except SyntaxError as e:
            self.report({'ERROR'}, f"Invalid expression syntax: {e}")
            return {'CANCELLED'}

        id_block = resolve_easydriver_id_block(item.id_name, item.id_type)
        if not id_block:
            self.report({'ERROR'}, f"'{item.id_name}' not found")
            return {'CANCELLED'}

        fcurve = find_driver_fcurve(id_block, item.data_path, item.array_index)
        if not fcurve:
            self.report({'ERROR'}, "Driver not found - try Scan again")
            return {'CANCELLED'}

        fcurve.driver.expression = self.new_expression
        context.view_layer.update()

        # Re-scan so curve_type/validity/value in the list reflect the edit immediately
        results = scan_easydriver_drivers()
        _populate_review_list(context, results)

        self.report({'INFO'}, "Expression updated")
        return {'FINISHED'}


class ANIM_OT_remove_reviewed_driver(bpy.types.Operator):
    """Remove one driver from the review list (and from the file)"""
    bl_idname = "anim.remove_reviewed_driver"
    bl_label = "Remove Driver"
    bl_description = "Delete this driver"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty()

    def execute(self, context):
        review_list = context.scene.ez_driver_review_list
        if self.index < 0 or self.index >= len(review_list):
            return {'CANCELLED'}

        item = review_list[self.index]
        id_block = resolve_easydriver_id_block(item.id_name, item.id_type)
        if id_block is not None:
            try:
                if item.array_index >= 0:
                    id_block.driver_remove(item.data_path, item.array_index)
                else:
                    id_block.driver_remove(item.data_path)
            except Exception as e:
                print(f"EasyDriver: could not remove driver: {e}")

        review_list.remove(self.index)
        if context.scene.ez_driver_review_index >= len(review_list):
            context.scene.ez_driver_review_index = max(0, len(review_list) - 1)

        self.report({'INFO'}, "Driver removed")
        return {'FINISHED'}


class ANIM_OT_remove_broken_reviewed_drivers(bpy.types.Operator):
    """Remove every driver in the review list that's currently broken"""
    bl_idname = "anim.remove_broken_reviewed_drivers"
    bl_label = "Remove Broken"
    bl_description = "Remove all drivers in the list that are broken (invalid expression or missing/deleted source)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        review_list = context.scene.ez_driver_review_list
        removed = 0
        # Iterate in reverse so removing an item doesn't shift indices we haven't visited yet
        for i in range(len(review_list) - 1, -1, -1):
            item = review_list[i]
            if item.expr_valid and item.source_valid:
                continue
            id_block = resolve_easydriver_id_block(item.id_name, item.id_type)
            if id_block is not None:
                try:
                    if item.array_index >= 0:
                        id_block.driver_remove(item.data_path, item.array_index)
                    else:
                        id_block.driver_remove(item.data_path)
                except Exception as e:
                    print(f"EasyDriver: could not remove driver: {e}")
            review_list.remove(i)
            removed += 1

        context.scene.ez_driver_review_index = 0
        self.report({'INFO'}, f"Removed {removed} broken driver(s)")
        return {'FINISHED'}


#---------------------------------------
# Registration - Dont forget to update!
#---------------------------------------
 
classes = (
    DriverRecorderProperties,
    ANIM_OT_record_from_min,
    ANIM_OT_record_from_max,
    POSE_OT_record_to_min_pose,
    POSE_OT_record_to_max_pose,
    MESH_OT_add_shapekey_target,
    MESH_OT_remove_shapekey_target,
    SCENE_OT_validate_path,
    SCENE_OT_add_path_target,
    SCENE_OT_remove_path_target,
    SCENE_OT_record_path_min,      # NEW
    SCENE_OT_record_path_max,      # NEW
    SCENE_OT_record_source_path_min,
    SCENE_OT_record_source_path_max,
    ANIM_OT_setup_custom_path_source,
    ANIM_OT_clear_custom_path_source,
    ANIM_OT_create_drivers,
    ANIM_OT_remove_drivers,
    SCENE_OT_clear_all,
    SCENE_OT_set_target_type,
    SCENE_OT_clear_targets,
    SCENE_OT_clear_source,
    OBJECT_OT_limit_source_transforms,
    OBJECT_OT_one_axis_source_limit,
    ANIM_OT_path_eyedropper,
    ANIM_OT_object_eyedropper,
    POSE_OT_remove_pose_bone,
    ANIM_OT_edit_target_value,
    ANIM_OT_toggle_fine_tune,
    ANIM_OT_close_fine_tune,
    MESH_OT_edit_shapekey_target,
    SCENE_OT_edit_path_target,
    ANIM_OT_mirror_source,
    ANIM_OT_mirror_targets,
    ANIM_OT_setup_custom_prop_source,
    ANIM_OT_clear_custom_prop_source,
    CustomPropBrowserItem,
    ANIM_OT_refresh_custom_prop_browser,
    ANIM_OT_add_custom_prop_entry,
    ANIM_OT_remove_custom_prop_entry,
    ANIM_OT_record_custom_prop_min,
    ANIM_OT_record_custom_prop_max,
    ANIM_OT_setup_shapekey_source,
    ANIM_OT_clear_shapekey_source,
    ANIM_OT_edit_shapekey_source,
    SCENE_OT_set_source_mode,
    MultiSourceSlotItem,
    ANIM_OT_add_multi_source_slot,
    ANIM_OT_remove_multi_source_slot,
    ANIM_OT_edit_multi_source_slot,
    ANIM_OT_move_multi_source_slot,
    ANIM_OT_clear_multi_source,
    EZDriverReviewItem,
    ANIM_OT_scan_easydriver_drivers,
    ANIM_OT_edit_driver_expression,
    ANIM_OT_remove_reviewed_driver,
    ANIM_OT_remove_broken_reviewed_drivers,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
