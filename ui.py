import bpy
from .core_functions import (
    get_to_bones_data, get_shapekey_list_data, get_path_list_data, auto_detect_path_type, parse_target_path
)

#---------------------------------------
# Version compatibility helpers
#---------------------------------------
def get_version_compatible_icons():
    """Return compatible icons based on Blender version"""
    version = bpy.app.version
    
    if version >= (4, 5, 0):
        return {
            'checkmark': 'CHECKMARK',
            'trash': 'TRASH',
            'remove': 'REMOVE',
            'plus': 'PLUS',
            'socket_on': 'NODE_SOCKET_GEOMETRY',
            'socket_off': 'NODE_SOCKET_MATERIAL',
            'preferences': 'PREFERENCES',
            'locked': 'LOCKED',
            'constraint': 'CONSTRAINT',
            'export': 'EXPORT',
            'import': 'IMPORT'
        }
    else:
        # Blender 4.0-4.3 compatible icons (these all exist in 4.0)
        return {
            'checkmark': 'CHECKMARK',  # This exists in 4.0
            'trash': 'TRASH',          # This exists in 4.0
            'remove': 'REMOVE',        # This exists in 4.0
            'plus': 'PLUS',            # This exists in 4.0
            'socket_on': 'RADIOBUT_ON',    # Use radio button for on state
            'socket_off': 'RADIOBUT_OFF',  # Use radio button for off state
            'preferences': 'PREFERENCES',   # This exists in 4.0
            'locked': 'LOCKED',            # This exists in 4.0
            'constraint': 'CONSTRAINT',     # This exists in 4.0
            'export': 'EXPORT',            # This exists in 4.0 (based on error list)
            'import': 'IMPORT'             # This exists in 4.0 (based on error list)
        }

def is_version_compatible(min_version):
    """Check if current Blender version meets minimum requirement"""
    return bpy.app.version >= min_version

#---------------------------------------
# UI
#---------------------------------------
class BONEMINMAX_PT_main_panel(bpy.types.Panel):
    bl_label = "Easy Driver"
    bl_idname = "BONEMINMAX_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Rigging"

    #---------------------------------------
    # Draw UI
    #---------------------------------------
    def draw(self, context):
        layout = self.layout
        props = context.scene.driver_recorder_props
        icons = get_version_compatible_icons()

        # Header with clear button
        header = layout.row()
        header.label(text="Driver Creator", icon='DRIVER')
        header.operator("scene.clear_all", text="", icon=icons['trash'])
        
        layout.separator()

        # UI COMPLEXITY TIER SELECTOR
        self.draw_complexity_selector(layout, props)

        layout.separator(factor=0.4)

        # SOURCE PANEL
        self.draw_source_panel(layout, props, context)
        
        # TARGET PANEL  
        self.draw_target_panel(layout, props, context)
        
        # ACTIONS PANEL
        self.draw_actions_panel(layout, props, context)

        # DRIVER REVIEW PANEL - More/Advanced only
        if props.ui_complexity != 'BASIC':
            self.draw_driver_review_panel(layout, context)

    def draw_complexity_selector(self, layout, props):
        """Basic / More / Advanced tier toggle - controls how much of the UI is shown."""
        row = layout.row(align=True)
        row.scale_y = 0.9
        for mode, label in (('BASIC', 'Basic'), ('MORE', 'More'), ('ADVANCED', 'Advanced')):
            row.prop_enum(props, "ui_complexity", mode, text=label)

    #---------------------------------------
    # Panels
    #---------------------------------------
    def draw_source_panel(self, layout, props, context):
        """Draw simplified source configuration with automatic mode detection."""
        icons = get_version_compatible_icons()
        
        # Collapsible source section
        box = layout.box()
        header = box.row()
        
        # Toggle icon
        icon = "TRIA_DOWN" if getattr(context.scene, "show_source", True) else "TRIA_RIGHT"
        header.prop(context.scene, "show_source", icon=icon, icon_only=True, emboss=False)
        
        # Title and status
        header.label(text="Source", icon=icons['export'])
        
        # Status indicator
        is_ready = self.get_source_status(props, context)
        if is_ready:
            header.label(text="", icon=icons['checkmark'])
        
        # Mirror button - only show for bone/object sources
        if props.from_bone or props.from_object:
            header.operator("anim.mirror_source", text="", icon='MOD_MIRROR')
        
        # Clear source button
        header.operator("scene.clear_source", text="", icon=icons['trash'])
        
        if not getattr(context.scene, "show_source", True):
            return
            
        col = box.column()

        # ── Source mode dropdown ── (More/Advanced only - Basic is transform-only) ──
        if props.ui_complexity != 'BASIC':
            mode_row = col.row(align=True)
            mode_row.prop(props, "from_source_type", text="Source")
            col.separator(factor=0.4)

        # World/Local space toggle - Advanced only, applies to bone/object transform sources
        if props.ui_complexity != 'BASIC' and props.from_source_type == 'BONE':
            space_row = col.row(align=True)
            space_row.prop(props, "source_use_world_space", toggle=True,
                           text="World Space" if props.source_use_world_space else "Local Space",
                           icon='WORLD' if props.source_use_world_space else 'ORIENTATION_LOCAL')
            col.separator(factor=0.3)

        if props.ui_complexity != 'BASIC' and props.from_source_type == 'CUSTOM_PROP':
            # ── Custom property source UI ───────────────────────────────────
            self.draw_custom_prop_source(col, props, context, icons)
        elif props.ui_complexity != 'BASIC' and props.from_source_type == 'SHAPEKEY':
            # ── Shape key source UI ──────────────────────────────────────────
            self.draw_shapekey_source(col, props, icons)
        elif props.ui_complexity != 'BASIC' and props.from_source_type == 'CUSTOM_PATH':
            # ── Custom path source UI ────────────────────────────────────────
            self.draw_custom_path_source(col, props, icons)
        else:
            # ── Transform source UI (bone / object) ─────────────────────────
            self.draw_transform_source(col, props, context, icons)

        # Multi-source blending - Advanced only
        if props.ui_complexity == 'ADVANCED':
            self.draw_multi_source_panel(col, props, context, icons)

    def draw_multi_source_panel(self, col, props, context, icons):
        """Combine two or more sources into a single driver input. Uses the
        same native list widget (template_list, +/- side column) as Driver
        Review and the Custom Property Browser, for a consistent feel."""
        scene = context.scene
        slots = scene.multi_source_slots
        combine_mode = props.multi_source_combine_mode
        distance_mismatch = (combine_mode == 'DISTANCE' and len(slots) not in (0, 2))
        ready = len(slots) >= 2 and not distance_mismatch

        outer = col.box()

        header = outer.row(align=True)
        header.prop(props, "multi_source_enabled", text="Multi-Source Blend", icon='MOD_ARRAY')
        if props.multi_source_enabled:
            if ready:
                header.label(text="", icon=icons['checkmark'])
            elif len(slots) > 0:
                header.label(text="", icon='ERROR')

        if not props.multi_source_enabled:
            return

        outer.separator(factor=0.3)

        if len(slots) == 0:
            hint = outer.row()
            hint.scale_y = 0.85
            hint.label(text="Configure a source above, then hit + to add it", icon='INFO')

        # ── Source list + side buttons (Add / Remove / Edit / Move) ─────────
        list_row = outer.row()
        list_row.template_list(
            "EZ_UL_multi_source_slots", "",
            scene, "multi_source_slots",
            scene, "multi_source_slot_index",
            rows=4
        )
        side = list_row.column(align=True)
        side.operator("anim.add_multi_source_slot", text="", icon='ADD')
        side.operator("anim.remove_multi_source_slot", text="", icon='REMOVE')
        side.separator()
        side.operator("anim.edit_multi_source_slot", text="", icon='GREASEPENCIL')
        side.separator()
        move_up = side.operator("anim.move_multi_source_slot", text="", icon='TRIA_UP')
        move_up.direction = 'UP'
        move_down = side.operator("anim.move_multi_source_slot", text="", icon='TRIA_DOWN')
        move_down.direction = 'DOWN'

        if len(slots) > 0:
            clear_row = outer.row()
            clear_row.scale_y = 0.8
            clear_row.operator("anim.clear_multi_source", text="Clear All", icon=icons['trash'])

        outer.separator(factor=0.4)

        # ── Combine mode + live preview + combined range, all together ──────
        settings = outer.column(align=True)
        settings.prop(props, "multi_source_combine_mode", text="Combine")

        n = len(slots) if slots else 2
        names = [f"Source {i+1}" for i in range(max(n, 2))]
        if combine_mode == 'ADD':
            preview = " + ".join(names)
        elif combine_mode == 'MULTIPLY':
            preview = " \u00d7 ".join(names)
        elif combine_mode == 'SUBTRACT':
            preview = " \u2212 ".join(names)
        else:  # DISTANCE
            preview = f"|{names[0]} \u2212 {names[1]}|"

        preview_row = settings.row()
        preview_row.scale_y = 0.8
        preview_row.label(text=f"Result = {preview}")

        if distance_mismatch:
            settings.label(text="Distance needs exactly 2 sources", icon='ERROR')

        range_row = settings.row(align=True)
        range_row.prop(props, "multi_source_from_min", text="Min")
        range_row.prop(props, "multi_source_from_max", text="Max")

        if len(slots) < 2:
            outer.label(text="Add at least 2 sources to finish", icon='INFO')

    def draw_custom_path_source(self, col, props, icons):
        """Draw the custom path source sub-panel - eyedropper + type-and-go
        path entry, then record Min/Max from the live value. Same pattern as
        the Path List target picker, applied to sourcing instead of driving."""
        is_set = props.source_custom_path_is_set

        if is_set:
            info = col.box()
            info.scale_y = 0.9
            info.label(text=props.source_custom_path_input, icon='DRIVER')
            range_row = info.row()
            range_row.label(text=f"Range: {props.source_path_min_value:.3g} → {props.source_path_max_value:.3g}",
                            icon='ORIENTATION_GIMBAL')
            action_row = col.row(align=True)
            action_row.operator("anim.clear_custom_path_source", text="Clear", icon=icons['trash'])
            return

        setup_box = col.box()

        path_row = setup_box.row(align=True)
        path_row.prop(props, "source_custom_path_input", text="Path")
        eyedropper = path_row.operator("anim.path_eyedropper", text="", icon='EYEDROPPER')
        eyedropper.target_field = "source_custom_path_input"
        eyedropper.active_flag_field = "source_path_eyedropper_active"

        if props.source_path_eyedropper_active:
            status_row = setup_box.row()
            status_row.alert = True
            status_row.label(text="Listening for property changes... (ESC to cancel)", icon='REC')
            path_row.enabled = False

        if not props.source_custom_path_input:
            setup_box.label(text="Type a path or use the eyedropper to pick one", icon='INFO')
            return

        # Try to detect type for button labels (Boolean vs Float)
        try:
            data_block, data_path, index = parse_target_path(props.source_custom_path_input)
            detected_type = auto_detect_path_type(data_block, data_path, index) if data_block else 'FLOAT'
        except Exception:
            detected_type = 'FLOAT'

        icons_local = get_version_compatible_icons()
        record_row = setup_box.row(align=True)
        record_row.scale_y = 1.2
        if detected_type == 'BOOLEAN':
            record_row.operator("scene.record_source_path_min", text="Record False",
                                icon=icons_local['socket_on'] if props.source_path_recorded_min else icons_local['socket_off'])
            record_row.operator("scene.record_source_path_max", text="Record True",
                                icon=icons_local['socket_on'] if props.source_path_recorded_max else icons_local['socket_off'])
        else:
            record_row.operator("scene.record_source_path_min", text="Record Min",
                                icon=icons_local['socket_on'] if props.source_path_recorded_min else icons_local['socket_off'])
            record_row.operator("scene.record_source_path_max", text="Record Max",
                                icon=icons_local['socket_on'] if props.source_path_recorded_max else icons_local['socket_off'])

        range_row = setup_box.row(align=True)
        range_row.prop(props, "source_path_min_value", text="Min")
        range_row.prop(props, "source_path_max_value", text="Max")

        can_set = bool(props.source_custom_path_input.strip())
        set_row = col.row()
        set_row.enabled = can_set
        set_row.scale_y = 1.2
        set_row.operator("anim.setup_custom_path_source", text="Set as Source", icon=icons['checkmark'])

    def draw_shapekey_source(self, col, props, icons):
        """Draw the shape-key source sub-panel (use a shape key's value to drive something else)."""
        is_set = props.shapekey_src_is_set

        if is_set:
            info = col.box()
            info.scale_y = 0.9
            row = info.row()
            obj = props.shapekey_src_object
            row.label(text=f"{obj.name if obj else '?'} › {props.shapekey_src_name}", icon='SHAPEKEY_DATA')
            range_row = info.row()
            range_row.label(text=f"Range: {props.shapekey_src_min:.3g} → {props.shapekey_src_max:.3g}",
                            icon='ORIENTATION_GIMBAL')
            action_row = col.row(align=True)
            if props.ui_complexity != 'BASIC':
                edit_op = action_row.operator("anim.edit_shapekey_source", text="", icon='GREASEPENCIL')
            action_row.operator("anim.clear_shapekey_source", text="Clear", icon=icons['trash'])
        else:
            setup_box = col.box()
            setup_box.prop(props, "shapekey_src_object", text="Object")

            obj = props.shapekey_src_object
            if obj and obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
                setup_box.prop_search(props, "shapekey_src_name",
                                      obj.data.shape_keys, "key_blocks", text="Shape Key")
            elif obj:
                setup_box.label(text="Object has no shape keys", icon='ERROR')

            range_row = setup_box.row(align=True)
            range_row.prop(props, "shapekey_src_min", text="Min")
            range_row.prop(props, "shapekey_src_max", text="Max")

            can_set = bool(obj and props.shapekey_src_name.strip())
            set_row = col.row()
            set_row.enabled = can_set
            set_row.scale_y = 1.2
            set_row.operator("anim.setup_shapekey_source", text="Set as Source",
                             icon=icons['checkmark'])

    def draw_custom_prop_source(self, col, props, context, icons):
        """Draw the custom property source sub-panel - browse, search, add,
        and remove custom properties on the selected object/bone, then pick
        one to use as the driver source."""
        is_set = props.custom_prop_is_set

        if is_set:
            # Compact summary when configured
            info = col.box()
            info.scale_y = 0.9
            row = info.row()
            obj = props.custom_prop_source_object
            bname = props.custom_prop_bone.strip()
            pname = props.custom_prop_name
            if bname:
                row.label(text=f"{obj.name if obj else '?'} › {bname} › {pname}", icon='DRIVER')
            else:
                row.label(text=f"{obj.name if obj else '?'} › {pname}", icon='DRIVER')
            range_row = info.row()
            range_row.label(text=f"Range: {props.custom_prop_min:.3g} → {props.custom_prop_max:.3g}",
                            icon='ORIENTATION_GIMBAL')
            action_row = col.row(align=True)
            action_row.operator("anim.clear_custom_prop_source", text="Clear", icon=icons['trash'])
            return

        setup_box = col.box()

        # Object / Armature picker (list auto-refreshes when this changes)
        setup_box.prop(props, "custom_prop_source_object", text="Object")

        obj = props.custom_prop_source_object
        if obj and obj.type == 'ARMATURE':
            setup_box.prop_search(props, "custom_prop_bone",
                                  obj.pose, "bones", text="Bone (opt.)")

        if not obj:
            setup_box.label(text="Select an object to browse its properties", icon='INFO')
            return

        setup_box.separator(factor=0.4)

        # ── Property browser: search + list + add/remove side buttons ───────
        scene = context.scene
        list_row = setup_box.row()
        list_row.template_list(
            "EZ_UL_custom_prop_browser", "",
            scene, "cp_browse_list",
            scene, "cp_browse_index",
            rows=4
        )
        side = list_row.column(align=True)
        side.operator("anim.add_custom_prop_entry", text="", icon='ADD')
        side.operator("anim.remove_custom_prop_entry", text="", icon='REMOVE')
        side.separator()
        side.operator("anim.refresh_custom_prop_browser", text="", icon='FILE_REFRESH')

        setup_box.separator(factor=0.4)

        # Selected property (set automatically by clicking a row above)
        selected_row = setup_box.row()
        if props.custom_prop_name.strip():
            selected_row.label(text=f"Selected: {props.custom_prop_name}", icon='EYEDROPPER')
        else:
            selected_row.label(text="Click a property above to select it", icon='INFO')

        # Min / Max
        range_row = setup_box.row(align=True)
        range_row.prop(props, "custom_prop_min", text="Min")
        range_row.prop(props, "custom_prop_max", text="Max")

        # Advanced: record min/max from the property's live value instead of typing numbers
        if props.ui_complexity == 'ADVANCED':
            record_row = setup_box.row(align=True)
            record_row.enabled = bool(props.custom_prop_name.strip())
            record_row.operator("anim.record_custom_prop_min", text="Record Min", icon='REC')
            record_row.operator("anim.record_custom_prop_max", text="Record Max", icon='REC')

        # Set button
        can_set = bool(obj and props.custom_prop_name.strip())
        set_row = col.row()
        set_row.enabled = can_set
        set_row.scale_y = 1.2
        set_row.operator("anim.setup_custom_prop_source", text="Set as Source",
                         icon=icons['checkmark'])

    def draw_transform_source(self, col, props, context, icons):
        """Draw bone / object transform source UI (original behaviour)."""
        # Record buttons
        row = col.row(align=True)
        row.scale_y = 1.2
        has_min = props.from_has_min if props.from_bone else props.from_object_has_min
        has_max = props.from_has_max if props.from_bone else props.from_object_has_max
        row.operator("anim.record_from_min", text="Record Min", 
                    icon=icons['socket_on'] if has_min else icons['socket_off'])
        row.operator("anim.record_from_max", text="Record Max", 
                    icon=icons['socket_on'] if has_max else icons['socket_off'])
        
        col.separator(factor=0.5)
        
        # Status display - show appropriate info based on what's recorded
        if props.from_bone or props.from_object:
            info = col.box()
            info.scale_y = 0.9
            
            # Show bone or object name with appropriate icon and fine tune button
            row = info.row()
            if props.from_bone:
                row.label(text=f"{props.from_armature}: {props.from_bone}", icon='BONE_DATA')
            elif props.from_object:
                row.label(text=props.from_object, icon='OBJECT_DATA')
            
            # Fine tune button
            row.operator("anim.toggle_fine_tune", text="FINE TUNE", icon=icons['preferences'])
            
            # Check if fine tune mode is active
            fine_tune_active = getattr(context.scene, "source_fine_tune_mode", False)
            
            if fine_tune_active:
                # Fine tune inputs
                col_tune = info.column()
                col_tune.separator(factor=0.3)
                
                # Manual source selection section
                selection_box = col_tune.box()
                selection_box.label(text="Change Source:", icon='OBJECT_DATA')
                
                # Show appropriate selection based on current source type
                if props.from_bone:
                    # Armature + Bone selection
                    selection_box.prop(props, "manual_source_armature", text="Armature")
                    if props.manual_source_armature:
                        selection_box.prop_search(props, "manual_source_bone", 
                                                props.manual_source_armature.pose, "bones", 
                                                text="Bone")
                else:
                    # Object selection
                    selection_box.prop(props, "manual_source_object", text="Object")
                
                # Apply button - only show if user has selected something different
                if props.from_bone and (props.manual_source_armature or props.manual_source_bone):
                    selection_box.operator("anim.apply_manual_source", text="Apply New Source", icon=icons['checkmark'])
                elif props.from_object and props.manual_source_object:
                    selection_box.operator("anim.apply_manual_source", text="Apply New Source", icon=icons['checkmark'])
                
                col_tune.separator(factor=0.5)
                
                # Min/Max value inputs
                row_inputs = col_tune.row(align=True)
                
                # Min input
                min_col = row_inputs.column()
                min_col.label(text="Min:")
                if props.from_bone:
                    min_col.prop(props, "fine_tune_min_value", text="")
                else:
                    min_col.prop(props, "fine_tune_object_min_value", text="")
                
                # Max input
                max_col = row_inputs.column()
                max_col.label(text="Max:")
                if props.from_bone:
                    max_col.prop(props, "fine_tune_max_value", text="")
                else:
                    max_col.prop(props, "fine_tune_object_max_value", text="")
                
                # Axis dropdown
                axis_row = col_tune.row()
                axis_row.label(text="Axis:")
                if props.from_bone:
                    axis_row.prop(props, "fine_tune_axis", text="")
                else:
                    axis_row.prop(props, "fine_tune_object_axis", text="")
                                
            else:
                # Normal status display
                row = info.row(align=True)
                detected_axis = props.from_detected_axis if props.from_bone else props.from_object_detected_axis
                if detected_axis:
                    axis_col = row.column()
                    axis_col.label(text=detected_axis, icon='ORIENTATION_GIMBAL')

    def draw_target_panel(self, layout, props, context):
        """Draw simplified target configuration."""
        icons = get_version_compatible_icons()
        
        # Collapsible target section
        box = layout.box()
        header = box.row()
        
        # Toggle icon
        icon = "TRIA_DOWN" if getattr(context.scene, "show_targets", True) else "TRIA_RIGHT"
        header.prop(context.scene, "show_targets", icon=icon, icon_only=True, emboss=False)
        
        # Title and count
        header.label(text="Targets", icon=icons['import'])
        
        target_count = self.get_target_count(props)
        if target_count > 0:
            header.label(text=f"({target_count})")
        
        # Mirror button - only show for pose and shapekey targets, and only if targets exist
        if target_count > 0 and props.target_type in ['CUSTOM_POSE', 'SHAPEKEY_LIST']:
            header.operator("anim.mirror_targets", text="", icon='MOD_MIRROR')
        
        # Clear targets button
        header.operator("scene.clear_targets", text="", icon=icons['trash'])
        
        if not getattr(context.scene, "show_targets", True):
            return
            
        # Content
        col = box.column()
        
        # Target type selection - 3 buttons side by side
        row = col.row(align=True)
        
        # Custom Pose button
        pose_btn = row.operator("scene.set_target_type", text="Pose", 
                            depress=(props.target_type == 'CUSTOM_POSE'))
        pose_btn.target_type = 'CUSTOM_POSE'
        
        # Shapekey List button
        shape_btn = row.operator("scene.set_target_type", text="ShapeKeys",
                                depress=(props.target_type == 'SHAPEKEY_LIST'))
        shape_btn.target_type = 'SHAPEKEY_LIST'
        
        # Path List button
        path_btn = row.operator("scene.set_target_type", text="Custom Paths",
                            depress=(props.target_type == 'PATH_LIST'))
        path_btn.target_type = 'PATH_LIST'
        
        col.separator(factor=0.5)
        
        # Target-specific UI
        if props.target_type == 'CUSTOM_POSE':
            self.draw_pose_targets(col, props)
        elif props.target_type == 'SHAPEKEY_LIST':
            self.draw_shapekey_targets(col, props)
        elif props.target_type == 'PATH_LIST':
            self.draw_path_targets(col, props, context)

    def draw_actions_panel(self, layout, props, context):
        """Draw action buttons."""
        icons = get_version_compatible_icons()
        
        box = layout.box()
        
        # Status check
        source_ready = self.get_source_status(props, context)
        target_count = self.get_target_count(props)
        can_create = source_ready and target_count > 0
        
        # Status message
        if can_create:
            box.label(text="Ready to create drivers", icon=icons['checkmark'])
        else:
            box.label(text="Set up source and targets", icon='INFO')
        
        # Action buttons
        col = box.column(align=True)
        col.scale_y = 1.3

        # Curve type dropdown - More/Advanced only (Basic always uses Linear)
        if props.ui_complexity != 'BASIC':
            curve_row = box.row(align=True)
            curve_row.scale_y = 1.0
            curve_row.prop(props, "driver_curve_type", text="Curve")
            if props.ui_complexity == 'ADVANCED':
                curve_row.prop(props, "invert_target_range", text="", icon='ARROW_LEFTRIGHT', toggle=True)

            col.separator(factor=0.3)

        # Create button
        create_row = col.row()
        create_row.enabled = bool(can_create)
        create_row.operator("anim.create_drivers", text="Create Drivers", icon=icons['plus'])
        
        # Constraint buttons section - side by side (More/Advanced only)
        if props.ui_complexity != 'BASIC':
            col.separator(factor=0.5)
            constraint_row = col.row(align=True)
            constraint_row.scale_y = 1.0
            constraint_row.enabled = bool(source_ready)
            
            # Lock to One Axis button
            constraint_row.operator("object.one_axis_source_limit", text="Lock to one axis", icon=icons['locked'])
            
            # Limit All Transforms button  
            constraint_row.operator("object.limit_source_transforms", text="Lock Recorded", icon=icons['constraint'])
        
        col.separator(factor=0.5)
        
        # Remove button
        col.operator("anim.remove_drivers", text="Remove Drivers", icon=icons['remove'])

    def draw_driver_review_panel(self, layout, context):
        """Draw the Driver Review section - lists every driver Easy Driver has
        created in this file, with per-item and bulk removal. The list is
        cached on the Scene (so it's saved with the file and persists across
        reload) and is re-populated automatically on file load, plus can be
        refreshed on demand with the Scan button.
        """
        icons = get_version_compatible_icons()
        scene = context.scene

        box = layout.box()
        header = box.row()
        header.label(text="Driver Review", icon='VIEWZOOM')
        header.operator("anim.scan_easydriver_drivers", text="Scan", icon='FILE_REFRESH')

        review_list = scene.ez_driver_review_list

        if len(review_list) == 0:
            box.label(text="No scan yet - click Scan", icon='INFO')
            return

        broken_count = sum(1 for it in review_list if not (it.expr_valid and it.source_valid))

        info_row = box.row()
        info_row.label(text=f"{len(review_list)} driver(s), {broken_count} broken")
        if broken_count > 0:
            info_row.operator("anim.remove_broken_reviewed_drivers", text="Remove Broken", icon=icons['trash'])

        box.template_list(
            "EZDRIVER_UL_driver_review", "",
            scene, "ez_driver_review_list",
            scene, "ez_driver_review_index",
            rows=4
        )

    #---------------------------------------
    # UI elements
    #---------------------------------------


    def draw_path_targets(self, layout, props, context):
        """Draw custom path target controls."""
        icons = get_version_compatible_icons()
        
        # Quick add section
        add_box = layout.box()
        add_box.label(text="Add Custom Path:", icon=icons['plus'])
        
        # Path input with eyedropper
        path_row = add_box.row(align=True)
        path_row.prop(props, "custom_path_input", text="Path")
        
        # Eyedropper button
        eyedropper = path_row.operator("anim.path_eyedropper", text="", icon='EYEDROPPER')
        
        # Show listening status and disable button when active
        if props.path_eyedropper_active:
            status_row = add_box.row()
            status_row.alert = True
            status_row.label(text="Listening for property changes... (ESC to cancel)", icon='REC')
            
            # Disable the eyedropper button when active
            path_row.enabled = False
        
        if props.custom_path_input:
            # Record buttons
            record_row = add_box.row(align=True)
            record_row.scale_y = 1.2
            
            # Try to detect type for button labels
            try:
                data_block, data_path, index = parse_target_path(props.custom_path_input)
                detected_type = auto_detect_path_type(data_block, data_path, index) if data_block else 'FLOAT'
            except:
                detected_type = 'FLOAT'
            
            # Record buttons - same functionality, different labels based on type
            if detected_type == 'BOOLEAN':
                # Boolean: Record False / Record True (but still records to min/max)
                record_row.operator("scene.record_path_min", text="Record False", 
                                icon=icons['socket_on'] if props.path_recorded_min else icons['socket_off'])
                record_row.operator("scene.record_path_max", text="Record True", 
                                icon=icons['socket_on'] if props.path_recorded_max else icons['socket_off'])
            else:
                # Float: Record Min / Record Max
                record_row.operator("scene.record_path_min", text="Record Min", 
                                icon=icons['socket_on'] if props.path_recorded_min else icons['socket_off'])
                record_row.operator("scene.record_path_max", text="Record Max", 
                                icon=icons['socket_on'] if props.path_recorded_max else icons['socket_off'])
            
            add_box.separator(factor=0.3)
            
            # Show detected type
            type_row = add_box.row()
            if detected_type == 'BOOLEAN':
                type_row.label(text="Boolean Property", icon='CHECKBOX_HLT')
            else:
                type_row.label(text="Float Property", icon='DRIVER')
            
            # Always show min/max inputs regardless of type
            row = add_box.row(align=True)
            if detected_type == 'BOOLEAN':
                row.prop(props, "path_min_value", text="False")
                row.prop(props, "path_max_value", text="True")
            else:
                row.prop(props, "path_min_value", text="Min")
                row.prop(props, "path_max_value", text="Max")
            
            # Add button
            add_box.operator("scene.add_path_target", text="Add", icon=icons['plus'])
        
        # Target list
        path_data = get_path_list_data(props)
        if path_data:
            layout.separator(factor=0.5)
            
            list_box = layout.box()
            list_box.label(text="Custom Paths:", icon='SCRIPT')
            
            for path, path_info in path_data.items():
                row = list_box.row()
                
                # Info
                col = row.column()
                # Shortened path
                display_path = path if len(path) <= 30 else path[:27] + "..."
                col.label(text=display_path)
                
                # Value info with type indicator - unified to use min/max for both types
                if path_info['type'] == 'BOOLEAN':
                    col.label(text=f"Bool: {path_info['min_value']:.2f} → {path_info['max_value']:.2f}", icon='CHECKBOX_HLT')
                else:
                    col.label(text=f"Float: {path_info['min_value']:.2f} → {path_info['max_value']:.2f}", icon='DRIVER')
                col.scale_y = 0.8
                
                # Buttons column
                btn_col = row.column(align=True)
                
                # Edit button
                edit_op = btn_col.operator("scene.edit_path_target", text="", icon='GREASEPENCIL')
                edit_op.key_to_edit = path
                
                # Remove button
                remove_op = btn_col.operator("scene.remove_path_target", text="", icon='X')
                remove_op.key_to_remove = path





    def draw_pose_targets(self, layout, props):
        """Draw pose target controls. Works for both pose bones (Pose Mode)
        and whole objects (Object Mode) - auto-detected from the current
        Blender interaction mode when you hit Record."""
        icons = get_version_compatible_icons()

        # Record buttons
        row = layout.row(align=True)
        row.scale_y = 1.2

        to_data = get_to_bones_data(props)

        has_min = any(bd.get('has_min') for bd in to_data.values())
        has_max = any(bd.get('has_max') for bd in to_data.values())

        row.operator("pose.record_to_min_pose", text="Record Min Pose",
                    icon=icons['socket_on'] if has_min else icons['socket_off'])
        row.operator("pose.record_to_max_pose", text="Record Max Pose",
                    icon=icons['socket_on'] if has_max else icons['socket_off'])

        # Target list — bones grouped by armature, objects grouped separately
        to_data = get_to_bones_data(props)
        if to_data:
            layout.separator(factor=0.5)

            armatures_seen = {}
            object_entries = []
            for key, bone_data in to_data.items():
                if bone_data.get('is_object'):
                    object_entries.append((key, bone_data))
                else:
                    arm = bone_data.get('armature', '?')
                    armatures_seen.setdefault(arm, []).append((key, bone_data))

            list_box = layout.box()

            show_edit = (props.ui_complexity == 'ADVANCED')

            for arm_name, entries in armatures_seen.items():
                # Armature header
                arm_row = list_box.row()
                arm_row.label(text=arm_name, icon='OUTLINER_DATA_ARMATURE')

                for key, bone_data in entries:
                    bone_display = bone_data.get('bone_name') or key.split('::')[-1]
                    self._draw_target_entry(list_box, key, bone_data, bone_display, 'BONE_DATA', 'pose.remove_pose_bone', show_edit)

            if object_entries:
                obj_header = list_box.row()
                obj_header.label(text="Objects", icon='OUTLINER_OB_MESH')

                for key, obj_data in object_entries:
                    obj_display = obj_data.get('object') or key.split('::')[-1]
                    self._draw_target_entry(list_box, key, obj_data, obj_display, 'OBJECT_DATA', 'pose.remove_pose_bone', show_edit)

    def _draw_target_entry(self, list_box, key, entry_data, display_name, icon, remove_idname, show_edit=False):
        """One row in the Custom Pose target list - shared by bone and object entries.
        show_edit (Advanced tier only) adds a per-axis fine-tune pencil button."""
        is_complete = entry_data.get('has_min') and entry_data.get('has_max')

        row = list_box.row()
        row.separator(factor=1.5)

        col = row.column()
        col.scale_y = 0.85

        if is_complete:
            col.label(text=display_name, icon=icon)
            changes = entry_data.get('detected_changes', [])
            if changes:
                if show_edit:
                    # One row per axis so each can get its own fine-tune button
                    for i, c in enumerate(changes):
                        change_row = col.row(align=True)
                        change_row.label(text=c['display'], icon='ORIENTATION_GIMBAL')
                        edit_op = change_row.operator("anim.edit_target_value", text="", icon='GREASEPENCIL')
                        edit_op.key = key
                        edit_op.change_index = i
                else:
                    col.label(text=" & ".join(c['display'] for c in changes),
                              icon='ORIENTATION_GIMBAL')
        else:
            has_min_b = entry_data.get('has_min', False)
            has_max_b = entry_data.get('has_max', False)
            status = "MIN ✓  MAX —" if has_min_b else "MIN —  MAX ✓" if has_max_b else "—"
            col.label(text=f"{display_name}  [{status}]", icon=icon)

        # Remove button — passes the full key ("Armature::Bone" or "OBJECT::Name")
        op = row.operator(remove_idname, text="", icon='X')
        op.bone_name = key

    def draw_shapekey_targets(self, layout, props):
        """Draw shapekey target controls."""
        icons = get_version_compatible_icons()
        
        # Quick add section
        add_box = layout.box()
        add_box.label(text="Add Shape Key:", icon=icons['plus'])
        
        # Object selection with eyedropper
        obj_row = add_box.row(align=True)
        obj_row.prop_search(props, "shapekey_target_object", bpy.data, "objects", text="Object")
        
        # Object eyedropper button
        eyedropper = obj_row.operator("anim.object_eyedropper", text="", icon='EYEDROPPER')
        eyedropper.target_property = "shapekey_target_object"
        
        # Show active status and disable when active
        if props.object_eyedropper_active:
            status_row = add_box.row()
            status_row.alert = True
            status_row.label(text="Click on object in viewport... (ESC to cancel)", icon='CURSOR')
            obj_row.enabled = False
        
        # Shape key selection
        if props.shapekey_target_object:
            obj = bpy.data.objects.get(props.shapekey_target_object)
            if obj and obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
                add_box.prop_search(props, "shapekey_name", obj.data.shape_keys, "key_blocks", text="Shape Key")
                
                if props.shapekey_name and props.shapekey_name != "Basis":
                    # Value range
                    row = add_box.row(align=True)
                    row.prop(props, "shapekey_min_value", text="Min")
                    row.prop(props, "shapekey_max_value", text="Max")
                    
                    # Add button
                    add_box.operator("mesh.add_shapekey_target", text="Add", icon=icons['plus'])
            else:
                add_box.label(text="No shape keys found", icon='INFO')
        
        # Target list
        shapekey_data = get_shapekey_list_data(props)
        if shapekey_data:
            layout.separator(factor=0.5)
            
            list_box = layout.box()
            list_box.label(text="Shape Keys:", icon='SHAPEKEY_DATA')
            
            for key, sk_data in shapekey_data.items():
                row = list_box.row()
                
                # Info
                col = row.column()
                col.label(text=f"{sk_data['object']}: {sk_data['shapekey']}")
                col.label(text=f"{sk_data['min_value']:.2f} → {sk_data['max_value']:.2f}")
                col.scale_y = 0.8
                
                # Buttons column
                btn_col = row.column(align=True)
                
                # Edit button
                edit_op = btn_col.operator("mesh.edit_shapekey_target", text="", icon='GREASEPENCIL')
                edit_op.key_to_edit = key
                
                # Remove button
                remove_op = btn_col.operator("mesh.remove_shapekey_target", text="", icon='X')
                remove_op.key_to_remove = key

    #---------------------------------------
    # Utils
    #---------------------------------------
    def get_source_status(self, props, context):
        """Check if source is properly configured (works for bone, object, custom prop, shape key, and multi-source)."""
        # Multi-source blend
        if props.multi_source_enabled:
            slots = context.scene.multi_source_slots
            if len(slots) < 2:
                return False
            if props.multi_source_combine_mode == 'DISTANCE' and len(slots) != 2:
                return False
            return props.multi_source_from_min != props.multi_source_from_max
        # Custom property source
        if props.custom_prop_is_set and props.custom_prop_source_object:
            return True
        # Shape key source
        if props.shapekey_src_is_set and props.shapekey_src_object:
            return True
        # Custom path source
        if props.source_custom_path_is_set and props.source_custom_path_input:
            return True
        # Check bone source
        if props.from_bone:
            return bool(props.from_has_min and props.from_has_max and props.from_detected_axis)
        # Check object source
        elif props.from_object:
            return bool(props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis)
        return False

    def get_target_count(self, props):
        """Get number of configured targets."""
        if props.target_type == 'CUSTOM_POSE':
            to_data = get_to_bones_data(props)
            return len([b for b in to_data.values() if b.get('has_min') and b.get('has_max')])
        elif props.target_type == 'SHAPEKEY_LIST':
            return len(get_shapekey_list_data(props))
        elif props.target_type == 'PATH_LIST':
            return len(get_path_list_data(props))
        return 0


#---------------------------------------
# Multi-Source Slots UIList
#---------------------------------------
class EZ_UL_multi_source_slots(bpy.types.UIList):
    """Row drawer for the Multi-Source blend list - icon | label | range."""

    SOURCE_ICONS = {
        'BONE_OBJECT': 'BONE_DATA',
        'CUSTOM_PROP': 'RNA',
        'SHAPEKEY': 'SHAPEKEY_DATA',
        'CUSTOM_PATH': 'DRIVER',
    }

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=f"{index + 1}.", icon=self.SOURCE_ICONS.get(item.kind, 'QUESTION'))
        row.label(text=item.label or item.source_name or '?')
        row.label(text=f"{item.from_min:.3g} \u2192 {item.from_max:.3g}")


#---------------------------------------
# Custom Property Browser UIList
#---------------------------------------
class EZ_UL_custom_prop_browser(bpy.types.UIList):
    """Row drawer for the Custom Property Browser - Property | Type | Value."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.prop_name)
        row.label(text=item.type_label)
        row.label(text=item.value_display)

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)

        if self.filter_name:
            needle = self.filter_name.lower()
            flt_flags = [
                self.bitflag_filter_item if needle in item.prop_name.lower() else 0
                for item in items
            ]
        else:
            flt_flags = [self.bitflag_filter_item] * len(items)

        return flt_flags, []


#---------------------------------------
# Driver Review UIList
#---------------------------------------
class EZDRIVER_UL_driver_review(bpy.types.UIList):
    """Row drawer for the Driver Review list."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        icons = get_version_compatible_icons()
        ok = item.expr_valid and item.source_valid
        props = context.scene.driver_recorder_props

        row = layout.row(align=True)
        row.label(text="", icon=icons['checkmark'] if ok else 'ERROR')

        info_col = row.column(align=True)
        info_col.scale_y = 0.85
        info_col.label(text=item.target_desc)
        sub = info_col.row()
        sub.scale_y = 0.85
        sub.label(text=f"from {item.source_desc}  ·  {item.curve_type.title()}")

        if props.ui_complexity == 'ADVANCED':
            edit_op = row.operator("anim.edit_driver_expression", text="", icon='SCRIPT')
            edit_op.index = index

        remove_op = row.operator("anim.remove_reviewed_driver", text="", icon=icons['trash'])
        remove_op.index = index

    def filter_items(self, context, data, propname):
        """Powers the built-in search box (funnel icon) on the Driver Review
        list - matches against target, source, and curve type text so you can
        type a bone/object/shapekey name and narrow a long list down fast."""
        items = getattr(data, propname)

        if self.filter_name:
            needle = self.filter_name.lower()
            flt_flags = []
            for item in items:
                haystack = f"{item.target_desc} {item.source_desc} {item.curve_type} {item.id_name}".lower()
                flt_flags.append(self.bitflag_filter_item if needle in haystack else 0)
        else:
            flt_flags = [self.bitflag_filter_item] * len(items)

        flt_neworder = []
        return flt_flags, flt_neworder

#---------------------------------------
# Registration
#---------------------------------------
classes = (
    BONEMINMAX_PT_main_panel,
    EZDRIVER_UL_driver_review,
    EZ_UL_multi_source_slots,
    EZ_UL_custom_prop_browser,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
