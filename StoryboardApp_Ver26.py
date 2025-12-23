bl_info = {
    "name": "Storyboard Suite (Definitive Build)",
    "author": "Dustin & Grok",
    "version": (6, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > UI Sidebar (N Panel) > Storyboard",
    "description": "The complete, stable, all-in-one storyboard system with reliable thumbnails and UUID workflow.",
    "category": "Scene"
}

import bpy
import os
import shutil
import uuid
import bpy.utils.previews

# =============================================================================
# === GLOBAL KEYS & PROPERTY GROUPS
# =============================================================================

UUID_KEY = "storyboard_uuid"
EXCLUSION_KEY = "storyboard_uuid_exclusion"

class StoryboardSceneSelectorItem(bpy.types.PropertyGroup):
    scene_index: bpy.props.IntProperty()
    selected: bpy.props.BoolProperty(name="Selected", default=False)

# =============================================================================
# === CORE UTILITY FUNCTIONS
# =============================================================================

def get_storyboard_collections():
    raw_cols = [c for c in bpy.data.collections if c.name.startswith("Storyboard_Scene_")]
    def get_index(col):
        try:
            suffix = col.name[len("Storyboard_Scene_"):]
            return int(suffix.split('.')[0].lstrip('0') or '0')
        except:
            return 9999
    return sorted(raw_cols, key=get_index)
def get_scene_index_from_name(col_name):
    if not col_name.startswith("Storyboard_Scene_"):
        return 9999
    suffix = col_name[len("Storyboard_Scene_"):]
    try:
        return int(suffix.split('.')[0])
    except:
        return 9999

def get_collection_name(index): 
    return f"Storyboard_Scene_{str(index).zfill(3)}"

def safe_redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()

def assign_uuid(obj):
    if obj and UUID_KEY not in obj:
        obj[UUID_KEY] = str(uuid.uuid4())

def hierarchical_copy(obj, target_col, copied_objects):
    if obj in copied_objects:
        return copied_objects[obj]
    new_obj = obj.copy()
    if obj.data:
        new_obj.data = obj.data.copy()
    assign_uuid(obj)
    new_obj[UUID_KEY] = obj[UUID_KEY]
    target_col.objects.link(new_obj)
    copied_objects[obj] = new_obj
    for child in obj.children:
        new_child = hierarchical_copy(child, target_col, copied_objects)
        new_child.parent = new_obj
        new_child.matrix_parent_inverse = child.matrix_parent_inverse.copy()
    return new_obj

def get_thumbnail_icon(filepath):
    previews = getattr(bpy.types.Scene, "storyboard_previews", None)
    if not previews:
        return 0
    if filepath not in previews:
        try:
            previews.load(filepath, filepath, 'IMAGE')
        except:
            return 0
    return previews[filepath].icon_id

def update_scene_selector_data(scene):
    scene.storyboard_scene_selector.clear()
    for col in get_storyboard_collections():
        item = scene.storyboard_scene_selector.add()
        item.scene_index = get_scene_index_from_name(col.name)
        item.selected = False

def get_camera_list_for_active_scene(self, context):
    items = [("NONE", "No Cameras", "")]
    active_idx = context.scene.storyboard_active_scene_index
    if active_idx >= 1:
        if col := bpy.data.collections.get(get_collection_name(active_idx)):
            cams = [obj for obj in col.objects if obj.type == 'CAMERA']
            items = [(cam.name, cam.name, "") for cam in sorted(cams, key=lambda o: o.name)]
    return items

def get_light_list_for_active_scene(self, context):
    items = [("NONE", "No Lights", "")]
    active_idx = context.scene.storyboard_active_scene_index
    if active_idx >= 1:
        if col := bpy.data.collections.get(get_collection_name(active_idx)):
            lights = [obj for obj in col.objects if obj.type == 'LIGHT']
            items = [(light.name, light.name, "") for light in sorted(lights, key=lambda o: o.name)]
    return items

def refresh_single_thumbnail(context, col):
    export_dir = bpy.path.abspath("//storyboard_exports/thumbnails/")
    try:
        os.makedirs(export_dir, exist_ok=True)
    except PermissionError:
        print("Permission denied creating thumbnail folder.")
        return False

    idx = get_scene_index_from_name(col.name)
    thumb_path = os.path.join(export_dir, f"Scene_{idx:03}_thumb.png")

    cam = next((obj for obj in col.objects if obj.type == 'CAMERA'), None)
    if not cam:
        return False

    scene = context.scene
    old_camera = scene.camera
    old_res_x = scene.render.resolution_x
    old_res_y = scene.render.resolution_y
    old_filepath = scene.render.filepath
    old_engine = scene.render.engine
    old_lock = scene.render.use_lock_interface

    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 480
    scene.render.resolution_y = 270
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = thumb_path
    scene.render.use_lock_interface = True
    scene.camera = cam

    override = {}
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override = {
                            'window': window,
                            'screen': window.screen,
                            'area': area,
                            'region': region,
                            'scene': scene,
                            'space_data': area.spaces.active,
                        }
                        break
                break
        if override:
            break

    previously_visible = [c for c in get_storyboard_collections() if not c.hide_viewport]
    for c in get_storyboard_collections():
        c.hide_viewport = True
    col.hide_viewport = False

    success = False
    try:
        if override:
            with context.temp_override(**override):
                bpy.ops.render.opengl(write_still=True, view_context=False)
        else:
            bpy.ops.render.opengl(write_still=True, view_context=False)
        success = True
    except Exception as e:
        print(f"Thumbnail render failed: {e}")

    for c in get_storyboard_collections():
        c.hide_viewport = True
    for c in previously_visible:
        c.hide_viewport = False

    scene.camera = old_camera
    scene.render.resolution_x = old_res_x
    scene.render.resolution_y = old_res_y
    scene.render.filepath = old_filepath
    scene.render.engine = old_engine
    scene.render.use_lock_interface = old_lock

    if success and os.path.exists(thumb_path):
        previews = bpy.types.Scene.storyboard_previews
        if thumb_path in previews:
            previews[thumb_path].reload()  # Fixed: reload instead of remove
        else:
            try:
                previews.load(thumb_path, thumb_path, 'IMAGE')
            except:
                pass
        safe_redraw()
        return True
    return False

# =============================================================================
# === OPERATORS
# =============================================================================

class STORYBOARD_OT_create_scene(bpy.types.Operator):
    bl_idname = "storyboard.create_scene"
    bl_label = "Create New Scene"

    def execute(self, context):
        collections = get_storyboard_collections()
        next_index = int(collections[-1].name.split("_")[-1]) + 1 if collections else 1
        new_col = bpy.data.collections.new(get_collection_name(next_index))
        context.scene.collection.children.link(new_col)

        cam_data = bpy.data.cameras.new(f"Camera_{next_index:03}")
        cam = bpy.data.objects.new(f"Camera_{next_index:03}", cam_data)
        cam.location = (0, -10, 5)
        cam.rotation_euler = (1.1, 0, 0)
        new_col.objects.link(cam)

        light_data = bpy.data.lights.new(name=f"KeyLight_{next_index:03}", type='POINT')
        light_obj = bpy.data.objects.new(name=f"KeyLight_{next_index:03}", object_data=light_data)
        light_obj.location = (4, 1, 5)
        light_data.energy = 1000
        new_col.objects.link(light_obj)

        new_col["annotation"] = ""
        new_col["duration"] = 0.0
        new_col["notes"] = ""
        new_col["locked"] = False
        new_col["camera_move"] = ""
        new_col["dialogue"] = ""

        update_scene_selector_data(context.scene)
        bpy.ops.storyboard.activate_scene('EXEC_DEFAULT', scene_number=next_index)

        # Auto-generate thumbnail for new scene
        refresh_single_thumbnail(context, new_col)

        return {'FINISHED'}

class STORYBOARD_OT_activate_scene(bpy.types.Operator):
    bl_idname = "storyboard.activate_scene"
    bl_label = "Activate Scene"
    scene_number: bpy.props.IntProperty()

    def execute(self, context):
        for col in get_storyboard_collections():
            col.hide_viewport = True
        if target_col := bpy.data.collections.get(get_collection_name(self.scene_number)):
            target_col.hide_viewport = False
            context.scene.storyboard_active_scene_index = self.scene_number
        safe_redraw()
        return {'FINISHED'}

class STORYBOARD_OT_next_scene(bpy.types.Operator):
    bl_idname = "storyboard.next_scene"
    bl_label = "Next Scene"

    def execute(self, context):
        collections = get_storyboard_collections()
        if not collections:
            return {'CANCELLED'}
        indices = [int(c.name.split("_")[-1]) for c in collections]
        try:
            current_pos = indices.index(context.scene.storyboard_active_scene_index)
            if current_pos + 1 < len(indices):
                bpy.ops.storyboard.activate_scene(scene_number=indices[current_pos + 1])
        except ValueError:
            bpy.ops.storyboard.activate_scene(scene_number=indices[0])
        return {'FINISHED'}

class STORYBOARD_OT_previous_scene(bpy.types.Operator):
    bl_idname = "storyboard.previous_scene"
    bl_label = "Previous Scene"

    def execute(self, context):
        collections = get_storyboard_collections()
        if not collections:
            return {'CANCELLED'}
        indices = [int(c.name.split("_")[-1]) for c in collections]
        try:
            current_pos = indices.index(context.scene.storyboard_active_scene_index)
            if current_pos - 1 >= 0:
                bpy.ops.storyboard.activate_scene(scene_number=indices[current_pos - 1])
        except ValueError:
            bpy.ops.storyboard.activate_scene(scene_number=indices[0])
        return {'FINISHED'}

class STORYBOARD_OT_look_through_camera(bpy.types.Operator):
    bl_idname = "storyboard.look_through_camera"
    bl_label = "Look Through Selected Camera"

    def execute(self, context):
        cam_obj = bpy.data.objects.get(context.scene.active_scene_camera)
        if not cam_obj:
            return {'CANCELLED'}

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.camera = cam_obj
                space.region_3d.view_perspective = 'CAMERA'
                break

        return {'FINISHED'}

class STORYBOARD_OT_fork_uuid(bpy.types.Operator):
    bl_idname = "storyboard.fork_uuid"
    bl_label = "Make Unique (Fork UUID)"
    @classmethod
    def poll(cls, context):
        return context.active_object and UUID_KEY in context.active_object

    def execute(self, context):
        obj_stack = [context.active_object]
        while obj_stack:
            obj = obj_stack.pop()
            obj[UUID_KEY] = str(uuid.uuid4())
            obj_stack.extend(obj.children)
        self.report({'INFO'}, f"'{context.active_object.name}' is now unique.")
        return {'FINISHED'}

class STORYBOARD_OT_propagate_object(bpy.types.Operator):
    bl_idname = "storyboard.propagate_object"
    bl_label = "Propagate Object"
    mode: bpy.props.EnumProperty(
        items=[('SELECTED', "Selected", ""), ('FORWARD', "Forward", ""), ('BACKWARD', "Backward", "")],
        default='SELECTED'
    )

    def execute(self, context):
        active_obj = context.active_object
        if not active_obj:
            return {'CANCELLED'}
        assign_uuid(active_obj)
        collections_map = {int(c.name.split("_")[-1]): c for c in get_storyboard_collections()}
        target_indices = set()

        if self.mode == 'SELECTED':
            target_indices = {item.scene_index for item in context.scene.storyboard_scene_selector if item.selected}
        else:
            current_idx = context.scene.storyboard_active_scene_index
            all_indices = collections_map.keys()
            if self.mode == 'FORWARD':
                target_indices = {idx for idx in all_indices if idx > current_idx}
            elif self.mode == 'BACKWARD':
                target_indices = {idx for idx in all_indices if idx < current_idx}

        count = 0
        for idx in target_indices:
            target_col = collections_map.get(idx)
            if target_col and not any(o.get(UUID_KEY) == active_obj[UUID_KEY] for o in target_col.objects):
                hierarchical_copy(active_obj, target_col, {})
                count += 1

        self.report({'INFO'}, f"Propagated object to {count} scenes.")
        return {'FINISHED'}

class STORYBOARD_OT_generate_all_thumbnails(bpy.types.Operator):
    bl_idname = "storyboard.generate_all_thumbnails"
    bl_label = "Generate All Thumbnails"

    def execute(self, context):
        for col in get_storyboard_collections():
            refresh_single_thumbnail(context, col)
        safe_redraw()
        self.report({'INFO'}, "All thumbnails refreshed.")
        return {'FINISHED'}

class STORYBOARD_OT_generate_thumbnail_single(bpy.types.Operator):
    bl_idname = "storyboard.generate_thumbnail_single"
    bl_label = "Refresh This Thumbnail"
    scene_number: bpy.props.IntProperty()

    def execute(self, context):
        if col := bpy.data.collections.get(get_collection_name(self.scene_number)):
            refresh_single_thumbnail(context, col)
            safe_redraw()
        return {'FINISHED'}

class STORYBOARD_OT_clear_thumbnail_cache(bpy.types.Operator):
    bl_idname = "storyboard.clear_thumbnail_cache"
    bl_label = "Clear Thumbnail Cache"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        thumb_dir = bpy.path.abspath("//storyboard_exports/thumbnails/")
        if os.path.exists(thumb_dir):
            shutil.rmtree(thumb_dir)
        if hasattr(bpy.types.Scene, "storyboard_previews"):
            bpy.utils.previews.remove(bpy.types.Scene.storyboard_previews)
            bpy.types.Scene.storyboard_previews = bpy.utils.previews.new()
        safe_redraw()
        self.report({'INFO'}, "Thumbnail cache cleared.")
        return {'FINISHED'}

class STORYBOARD_OT_add_camera_from_view(bpy.types.Operator):
    bl_idname = "storyboard.add_camera_from_view"
    bl_label = "Add Camera From View"

    def execute(self, context):
        active_col = bpy.data.collections.get(get_collection_name(context.scene.storyboard_active_scene_index))
        if not active_col:
            return {'CANCELLED'}
        bpy.ops.object.camera_add(align='VIEW')
        new_cam = context.active_object
        for col in list(new_cam.users_collection):
            col.objects.unlink(new_cam)
        active_col.objects.link(new_cam)
        return {'FINISHED'}

class STORYBOARD_OT_add_light(bpy.types.Operator):
    bl_idname = "storyboard.add_light"
    bl_label = "Add Light"

    def execute(self, context):
        active_col = bpy.data.collections.get(get_collection_name(context.scene.storyboard_active_scene_index))
        if not active_col:
            return {'CANCELLED'}
        light_data = bpy.data.lights.new(name="Point", type='POINT')
        light_obj = bpy.data.objects.new(name="Point", object_data=light_data)
        active_col.objects.link(light_obj)
        light_obj.location = context.scene.cursor.location
        return {'FINISHED'}

class STORYBOARD_OT_delete_scene(bpy.types.Operator):
    bl_idname = "storyboard.delete_scene"
    bl_label = "Delete Active Scene"
    scene_number: bpy.props.IntProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        current_index = self.scene_number
        col_to_delete = bpy.data.collections.get(get_collection_name(current_index))
        if not col_to_delete:
            return {'CANCELLED'}

        for obj in list(col_to_delete.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col_to_delete)

        # Renumber remaining scenes
        for col in get_storyboard_collections():
            idx = get_scene_index_from_name(col.name)
            if idx > current_index:
                col.name = get_collection_name(idx - 1)

        new_active = min(current_index - 1, len(get_storyboard_collections()))
        if new_active > 0 and get_storyboard_collections():
            bpy.ops.storyboard.activate_scene(scene_number=new_active)
        else:
            context.scene.storyboard_active_scene_index = 0

        update_scene_selector_data(context.scene)
        return {'FINISHED'}

class STORYBOARD_OT_assign_uuid(bpy.types.Operator):
    bl_idname = "storyboard.assign_uuid"
    bl_label = "Assign UUID"

    def execute(self, context):
        if context.active_object:
            assign_uuid(context.active_object)
        return {'FINISHED'}

class STORYBOARD_OT_toggle_exclusion(bpy.types.Operator):
    bl_idname = "storyboard.toggle_exclusion"
    bl_label = "Toggle Exclusion"

    def execute(self, context):
        obj = context.active_object
        if not obj or UUID_KEY not in obj:
            return {'CANCELLED'}
        current_idx = str(context.scene.storyboard_active_scene_index)
        exclusions = set(obj.get(EXCLUSION_KEY, "").split(','))
        if current_idx in exclusions:
            exclusions.remove(current_idx)
        else:
            exclusions.add(current_idx)
        obj[EXCLUSION_KEY] = ",".join(sorted(filter(None, exclusions)))
        return {'FINISHED'}

class STORYBOARD_OT_uuid_update_transforms(bpy.types.Operator):
    bl_idname = "storyboard.uuid_update_transforms"
    bl_label = "Sync Transforms"

    def execute(self, context):
        obj = context.active_object
        if not obj or UUID_KEY not in obj:
            return {'CANCELLED'}
        uuid_val = obj[UUID_KEY]
        exclusions = set(obj.get(EXCLUSION_KEY, "").split(','))
        for col in get_storyboard_collections():
            idx = str(int(col.name.split("_")[-1]))
            if idx in exclusions:
                continue
            for o in col.objects:
                if o.get(UUID_KEY) == uuid_val and o != obj:
                    o.location = obj.location
                    o.rotation_euler = obj.rotation_euler
                    o.scale = obj.scale
        return {'FINISHED'}

class STORYBOARD_OT_refresh_data(bpy.types.Operator):
    bl_idname = "storyboard.refresh_data"
    bl_label = "Refresh Data"

    def execute(self, context):
        update_scene_selector_data(context.scene)
        safe_redraw()
        return {'FINISHED'}

class STORYBOARD_OT_export_metadata(bpy.types.Operator):
    bl_idname = "storyboard.export_metadata"
    bl_label = "Export Metadata"

    def execute(self, context):
        export_dir = bpy.path.abspath("//storyboard_exports/")
        os.makedirs(export_dir, exist_ok=True)
        txt_path = os.path.join(export_dir, "storyboard_master.txt")
        csv_path = os.path.join(export_dir, "storyboard_master.csv")
        total_duration = 0.0

        with open(txt_path, "w", encoding='utf-8') as txt, open(csv_path, "w", newline='', encoding='utf-8') as csv_f:
            import csv
            writer = csv.writer(csv_f)
            writer.writerow(["Scene", "Annotation", "Camera Move", "Dialogue", "Duration (s)", "Notes"])
            for col in get_storyboard_collections():
                idx = get_scene_index_from_name(col.name)
                duration = col.get("duration", 0.0)
                total_duration += duration
                data = [
                    f"{idx:03}",
                    col.get("annotation", ""),
                    col.get("camera_move", ""),
                    col.get("dialogue", ""),
                    f"{duration:.2f}",
                    col.get("notes", "")
                ]
                writer.writerow(data)
                txt.write(f"Scene {data[0]} | Annotation: {data[1]} | Camera: {data[2]} | Dialogue: {data[3]} | Duration: {data[4]}s | Notes: {data[5]}\n")
            txt.write(f"\nTOTAL RUNTIME: {total_duration:.2f} seconds\n")
            writer.writerow([])
            writer.writerow(["TOTAL RUNTIME (s)", f"{total_duration:.2f}"])

        self.report({'INFO'}, "Metadata exported.")
        return {'FINISHED'}
class STORYBOARD_OT_move_scene_up(bpy.types.Operator):
    bl_idname = "storyboard.move_scene_up"
    bl_label = "Move Scene Up"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        collections = get_storyboard_collections()
        if len(collections) < 2:
            return {'CANCELLED'}

        current_idx = context.scene.storyboard_active_scene_index
        if current_idx <= 1:
            self.report({'INFO'}, "Already at first scene")
            return {'CANCELLED'}

        pos = next(i for i, col in enumerate(collections) if int(col.name.split("_")[-1]) == current_idx)
        if pos == 0:
            return {'CANCELLED'}

        # Swap with previous
        collections[pos], collections[pos - 1] = collections[pos - 1], collections[pos]

        # Renumber all sequentially
        for new_pos, col in enumerate(collections, start=1):
            new_name = get_collection_name(new_pos)
            if col.name != new_name:
                old_path = bpy.path.abspath(f"//storyboard_exports/thumbnails/Scene_{int(col.name.split('_')[-1]):03}_thumb.png")
                if os.path.exists(old_path):
                    os.remove(old_path)
                col.name = new_name

        context.scene.storyboard_active_scene_index = current_idx - 1
        update_scene_selector_data(context.scene)
        safe_redraw()
        self.report({'INFO'}, f"Moved scene {current_idx:03} up")
        return {'FINISHED'}

class STORYBOARD_OT_move_scene_down(bpy.types.Operator):
    bl_idname = "storyboard.move_scene_down"
    bl_label = "Move Scene Down"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        collections = get_storyboard_collections()
        if len(collections) < 2:
            return {'CANCELLED'}

        current_idx = context.scene.storyboard_active_scene_index
        if current_idx >= len(collections):
            self.report({'INFO'}, "Already at last scene")
            return {'CANCELLED'}

        pos = next(i for i, col in enumerate(collections) if int(col.name.split("_")[-1]) == current_idx)
        if pos >= len(collections) - 1:
            return {'CANCELLED'}

        # Swap with next
        collections[pos], collections[pos + 1] = collections[pos + 1], collections[pos]

        # Renumber all
        for new_pos, col in enumerate(collections, start=1):
            new_name = get_collection_name(new_pos)
            if col.name != new_name:
                old_path = bpy.path.abspath(f"//storyboard_exports/thumbnails/Scene_{int(col.name.split('_')[-1]):03}_thumb.png")
                if os.path.exists(old_path):
                    os.remove(old_path)
                col.name = new_name

        context.scene.storyboard_active_scene_index = current_idx + 1
        update_scene_selector_data(context.scene)
        safe_redraw()
        self.report({'INFO'}, f"Moved scene {current_idx:03} down")
        return {'FINISHED'}
class STORYBOARD_OT_cleanup_scenes(bpy.types.Operator):
    bl_idname = "storyboard.cleanup_scenes"
    bl_label = "Force Cleanup & Renumber"
    bl_description = "Force clean naming for collections, cameras, and lights; fix order and thumbnails"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        raw_cols = [c for c in bpy.data.collections if c.name.startswith("Storyboard_Scene_")]
        if not raw_cols:
            self.report({'INFO'}, "No storyboard scenes found")
            return {'FINISHED'}

        old_active_idx = context.scene.storyboard_active_scene_index
        old_active_col = bpy.data.collections.get(get_collection_name(old_active_idx)) if old_active_idx > 0 else None

        # Use safe sorting
        sorted_cols = get_storyboard_collections()

        renamed_count = 0
        for new_idx, col in enumerate(sorted_cols, start=1):
            new_col_name = get_collection_name(new_idx)
            old_idx_str = f"{get_scene_index_from_name(col.name):03}"

            if col.name != new_col_name:
                # Delete old thumbnail
                old_path = bpy.path.abspath(f"//storyboard_exports/thumbnails/Scene_{old_idx_str}_thumb.png")
                if os.path.exists(old_path):
                    os.remove(old_path)
                col.name = new_col_name
                renamed_count += 1

            new_idx_str = f"{new_idx:03}"

            # Rename camera
            cam = next((o for o in col.objects if o.type == 'CAMERA'), None)
            if cam and not cam.name.startswith(f"Camera_{new_idx_str}"):
                cam.name = f"Camera_{new_idx_str}"

            # Rename point light (KeyLight)
            light = next((o for o in col.objects if o.type == 'LIGHT' and o.name.startswith("KeyLight")), None)
            if light and not light.name.startswith(f"KeyLight_{new_idx_str}"):
                light.name = f"KeyLight_{new_idx_str}"

        # Restore active scene
        new_active_idx = 1
        if old_active_col:
            try:
                new_active_idx = next(i + 1 for i, c in enumerate(sorted_cols) if c == old_active_col)
            except StopIteration:
                new_active_idx = 1
        context.scene.storyboard_active_scene_index = new_active_idx
        bpy.ops.storyboard.activate_scene(scene_number=new_active_idx)

        # Regenerate thumbnails with new names
        for col in sorted_cols:
            refresh_single_thumbnail(context, col)

        update_scene_selector_data(context.scene)
        safe_redraw()

        self.report({'INFO'}, f"Cleanup complete: {renamed_count} collections renamed, cameras/lights updated, thumbnails refreshed")
        return {'FINISHED'}
# Next line will be your first panel: class STORYBOARD_PT_scene_creation_panel...


# =============================================================================
# === UI PANELS
# =============================================================================

class STORYBOARD_PT_scene_creation_panel(bpy.types.Panel):
    bl_label = "Creation & Navigation"
    bl_idname = "STORYBOARD_PT_scene_creation_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Storyboard'
    bl_order = 0

    def draw(self, context):
        layout = self.layout.column(align=True)
        layout.operator("storyboard.create_scene", icon='ADD')
        row = layout.row(align=True)
        row.operator("storyboard.add_camera_from_view")
        row.operator("storyboard.add_light")
        nav = layout.row(align=True)
        nav.operator("storyboard.previous_scene", icon='FRAME_PREV')
        nav.operator("storyboard.next_scene", icon='FRAME_NEXT')
        cleanup = layout.row()
        cleanup.operator("storyboard.cleanup_scenes", icon='FILE_REFRESH')
        reorder = layout.row(align=True)
        reorder.operator("storyboard.move_scene_up", icon='TRIA_UP')
        reorder.operator("storyboard.move_scene_down", icon='TRIA_DOWN')


class STORYBOARD_PT_scene_review_panel(bpy.types.Panel):
    bl_label = "Scene Review"
    bl_idname = "STORYBOARD_PT_scene_review_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Storyboard'
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "storyboard_safe_mode", text="Director Safe Mode", icon='LOCKED')
        layout.separator()

        if not get_storyboard_collections():
            layout.label(text="No scenes created yet.")
            return

        for col in get_storyboard_collections():
            suffix = col.name[len("Storyboard_Scene_"):]
            idx = int(suffix.split('.')[0])
            is_active = scene.storyboard_active_scene_index == idx
            box = layout.box()
            row = box.row(align=True)
            row.operator("storyboard.activate_scene", text=f"Scene {idx:03}", emboss=is_active).scene_number = idx

            disable = scene.storyboard_safe_mode or col.get("locked", False)
            edit_row = row.row(align=True)
            edit_row.enabled = not disable
            edit_row.prop(col, '["annotation"]', text="")
            edit_row.prop(col, '["locked"]', text="", icon='LOCKED' if col.get("locked") else 'UNLOCKED', emboss=False)

            row.operator("storyboard.delete_scene", text="", icon='TRASH', emboss=False).scene_number = idx

            if is_active:
                details = box.box()
                details.enabled = not disable
                details.prop(col, '["annotation"]', text="Title")
                details.prop(col, '["duration"]')
                details.prop(col, '["camera_move"]', text="Camera")
                details.prop(col, '["dialogue"]', text="Dialogue")
                details.prop(col, '["notes"]', text="Notes")
                cam_row = details.row(align=True)
                cam_row.prop(scene, "active_scene_camera", text="Active Camera")
                cam_row.operator("storyboard.look_through_camera", text="", icon='VIEW_CAMERA')
                details.row(align=True).prop(scene, "active_scene_light", text="Active Light")

class STORYBOARD_PT_thumbnail_browser_panel(bpy.types.Panel):
    bl_label = "Thumbnail Browser"
    bl_idname = "STORYBOARD_PT_thumbnail_browser_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Storyboard'
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.operator("storyboard.generate_all_thumbnails", icon='RENDER_RESULT')
        row.operator("storyboard.clear_thumbnail_cache", text="", icon='TRASH')
        layout.separator()

        for col in get_storyboard_collections():
            suffix = col.name[len("Storyboard_Scene_"):]
            idx = int(suffix.split('.')[0])
            box = layout.box()
            main_row = box.row()

            thumb_col = main_row.column()
            path = bpy.path.abspath(f"//storyboard_exports/thumbnails/Scene_{idx:03}_thumb.png")
            if os.path.exists(path):
                thumb_col.template_icon(icon_value=get_thumbnail_icon(path), scale=8.0)
            else:
                thumb_col.label(text="[No Thumbnail]")

            info_col = main_row.column()
            info_col.label(text=f"Scene {idx:03}: {col.get('annotation', '')}")
            op = info_col.operator("storyboard.generate_thumbnail_single", text="Refresh", icon='FILE_REFRESH')
            op.scene_number = idx

class STORYBOARD_PT_active_object_panel(bpy.types.Panel):
    bl_label = "Active Object (UUID)"
    bl_idname = "STORYBOARD_PT_active_object_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Storyboard'
    bl_order = 3

    @classmethod
    def poll(cls, context):
        return context.active_object and context.scene.storyboard_active_scene_index >= 1

    def draw(self, context):
        layout = self.layout.box()
        obj = context.active_object
        layout.label(text=f"Object: {obj.name}")
        if UUID_KEY in obj:
            layout.label(text=f"UUID: {obj[UUID_KEY][:8]}...")
            layout.operator("storyboard.fork_uuid", icon='UNLINKED')
            layout.operator("storyboard.toggle_exclusion")
            layout.operator("storyboard.uuid_update_transforms")
        else:
            layout.operator("storyboard.assign_uuid")

class STORYBOARD_PT_propagation_panel(bpy.types.Panel):
    bl_label = "Object Propagation"
    bl_idname = "STORYBOARD_PT_propagation_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Storyboard'
    bl_order = 4

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Propagate: {context.active_object.name}")

        box = layout.box()
        row = box.row()
        row.label(text="Target Scenes:")
        row.operator("storyboard.refresh_data", text="", icon='FILE_REFRESH')

        for item in context.scene.storyboard_scene_selector:
            layout.prop(item, "selected", text=f"Scene {item.scene_index:03}")

        col = layout.column(align=True)
        op = col.operator("storyboard.propagate_object", text="Propagate to Selected")
        op.mode = 'SELECTED'

        row = col.row(align=True)
        row.operator("storyboard.propagate_object", text="Hold Backward").mode = 'BACKWARD'
        row.operator("storyboard.propagate_object", text="Hold Forward").mode = 'FORWARD'

class STORYBOARD_PT_data_management_panel(bpy.types.Panel):
    bl_label = "Data Management"
    bl_idname = "STORYBOARD_PT_data_management_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Storyboard'
    bl_order = 98
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.operator("storyboard.export_metadata")

class STORYBOARD_PT_danger_zone_panel(bpy.types.Panel):
    bl_label = "Danger Zone"
    bl_idname = "STORYBOARD_PT_danger_zone_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Storyboard'
    bl_order = 99
    bl_options = {'DEFAULT_CLOSED'}
        
    def draw(self, context):
        layout = self.layout.box().column()
        layout.alert = True
        op = layout.operator("storyboard.delete_scene", icon='TRASH')
        op.scene_number = context.scene.storyboard_active_scene_index
        
        layout.separator()
        layout.operator("storyboard.cleanup_scenes", icon='BRUSH_DATA')  # or 'FILE_REFRESH'

    @classmethod
    def poll(cls, context):
        return context.scene.storyboard_active_scene_index >= 1

    def draw(self, context):
        layout = self.layout.box().column()
        layout.alert = True
        op = layout.operator("storyboard.delete_scene", icon='TRASH')
        op.scene_number = context.scene.storyboard_active_scene_index

# =============================================================================
# === REGISTRATION
# =============================================================================

classes = (
    StoryboardSceneSelectorItem,
    STORYBOARD_OT_create_scene,
    STORYBOARD_OT_activate_scene,
    STORYBOARD_OT_next_scene,
    STORYBOARD_OT_previous_scene,
    STORYBOARD_OT_cleanup_scenes,
    STORYBOARD_OT_look_through_camera,
    STORYBOARD_OT_assign_uuid,
    STORYBOARD_OT_toggle_exclusion,
    STORYBOARD_OT_fork_uuid,
    STORYBOARD_OT_propagate_object,
    STORYBOARD_OT_uuid_update_transforms,
    STORYBOARD_OT_generate_all_thumbnails,
    STORYBOARD_OT_generate_thumbnail_single,
    STORYBOARD_OT_clear_thumbnail_cache,
    STORYBOARD_OT_add_camera_from_view,
    STORYBOARD_OT_add_light,
    STORYBOARD_OT_delete_scene,
    STORYBOARD_OT_refresh_data,
    STORYBOARD_OT_export_metadata,
    STORYBOARD_OT_move_scene_up,      # ← add here
    STORYBOARD_OT_move_scene_down,    # ← add here
    STORYBOARD_PT_scene_creation_panel,
    STORYBOARD_PT_scene_review_panel,
    STORYBOARD_PT_thumbnail_browser_panel,
    STORYBOARD_PT_active_object_panel,
    STORYBOARD_PT_propagation_panel,
    STORYBOARD_PT_data_management_panel,
    STORYBOARD_PT_danger_zone_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.storyboard_previews = bpy.utils.previews.new()
    bpy.types.Scene.storyboard_safe_mode = bpy.props.BoolProperty(name="Director Safe Mode", default=False)
    bpy.types.Scene.storyboard_active_scene_index = bpy.props.IntProperty(name="Active Scene Index", default=0, min=0)
    bpy.types.Scene.active_scene_camera = bpy.props.EnumProperty(name="Scene Camera", items=get_camera_list_for_active_scene)
    bpy.types.Scene.active_scene_light = bpy.props.EnumProperty(name="Scene Light", items=get_light_list_for_active_scene)
    bpy.types.Scene.storyboard_scene_selector = bpy.props.CollectionProperty(type=StoryboardSceneSelectorItem)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    if hasattr(bpy.types.Scene, "storyboard_previews"):
        bpy.utils.previews.remove(bpy.types.Scene.storyboard_previews)
        del bpy.types.Scene.storyboard_previews

    for prop in ("storyboard_safe_mode", "storyboard_active_scene_index", "active_scene_camera", "active_scene_light", "storyboard_scene_selector"):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)

if __name__ == "__main__":
    register()