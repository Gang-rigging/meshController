# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Zhenggang Deng

"""
Mesh Control Manager UI
Run via:
    import meshControlManagerUI
    meshControlManagerUI.show()
"""

from PySide2 import QtWidgets, QtCore, QtGui
import maya.cmds as cmds

OVERLAY_SHAPE = "meshControlModeOverlayShape"
SELECTED_OVERLAY_SHAPE = "meshControlModeSelectedOverlayShape"
SELECT_PARENT_ATTR = "meshControlSelectParent"
DOCS_URL = "https://www.cgdzg.com/docs/meshController-docs.html"
APP_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_tracked_paths():
    if not cmds.objExists(OVERLAY_SHAPE):
        return []
    try:
        raw = cmds.getAttr(OVERLAY_SHAPE + ".trackedMeshPaths") or ""
        return [p for p in raw.split(",") if p.strip()]
    except Exception:
        return []


def _short_name(dag_path):
    return dag_path.split("|")[-1] or dag_path


def _mesh_transform(dag_path):
    if not dag_path or not cmds.objExists(dag_path):
        return None
    if cmds.nodeType(dag_path) == "mesh":
        parents = cmds.listRelatives(dag_path, parent=True, fullPath=True) or []
        return parents[0] if parents else None
    shapes = cmds.listRelatives(dag_path, shapes=True, fullPath=True, type="mesh") or []
    return dag_path if shapes else None


def _ensure_select_parent_attr(transform):
    if not transform or not cmds.objExists(transform):
        return False
    plug = transform + "." + SELECT_PARENT_ATTR
    if not cmds.objExists(plug):
        cmds.addAttr(transform, longName=SELECT_PARENT_ATTR, attributeType="bool", defaultValue=False)
    cmds.setAttr(plug, keyable=False, channelBox=False)
    return True


def _get_select_parent(path):
    transform = _mesh_transform(path)
    if not transform:
        return False
    plug = transform + "." + SELECT_PARENT_ATTR
    if not cmds.objExists(plug):
        return False
    return bool(cmds.getAttr(plug))


def _set_select_parent(paths, value):
    for path in paths:
        transform = _mesh_transform(path)
        if _ensure_select_parent_attr(transform):
            cmds.setAttr(transform + "." + SELECT_PARENT_ATTR, bool(value))


def _select_mesh_transforms(paths):
    targets = []
    seen = set()
    for path in paths:
        target = _mesh_transform(path) or path
        if not target or not cmds.objExists(target) or target in seen:
            continue
        targets.append(target)
        seen.add(target)
    if not targets:
        cmds.warning("No valid mesh transforms to select.")
        return
    cmds.select(targets, replace=True)


def _overlay_shapes():
    return [s for s in (OVERLAY_SHAPE, SELECTED_OVERLAY_SHAPE) if cmds.objExists(s)]


def _get_overlay_bool(attr, default=False):
    for shape in _overlay_shapes():
        plug = shape + "." + attr
        if cmds.objExists(plug):
            return bool(cmds.getAttr(plug))
    return default


def _set_overlay_bool(attr, value, selected_too=True):
    shapes = _overlay_shapes() if selected_too else ([OVERLAY_SHAPE] if cmds.objExists(OVERLAY_SHAPE) else [])
    for shape in shapes:
        plug = shape + "." + attr
        if cmds.objExists(plug):
            cmds.setAttr(plug, bool(value))


def _command_exists(command):
    try:
        cmds.help(command)
        return True
    except Exception:
        return False


def _open_documentation():
    if not QtGui.QDesktopServices.openUrl(QtCore.QUrl(DOCS_URL)):
        cmds.warning("Could not open documentation: " + DOCS_URL)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class _MeshListWidget(QtWidgets.QListWidget):
    def __init__(self, parent=None):
        super(_MeshListWidget, self).__init__(parent)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setMinimumHeight(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Ignored)

    def populate(self, dag_paths):
        selected = set(self.selected_paths())
        self.blockSignals(True)
        self.clear()
        try:
            for path in dag_paths:
                item = QtWidgets.QListWidgetItem(_short_name(path))
                item.setData(QtCore.Qt.UserRole, path)
                item.setToolTip(path)
                self.addItem(item)
                if path in selected:
                    item.setSelected(True)
        finally:
            self.blockSignals(False)

    def selected_paths(self):
        return [i.data(QtCore.Qt.UserRole) for i in self.selectedItems()]

    def all_paths(self):
        return [self.item(r).data(QtCore.Qt.UserRole) for r in range(self.count())]


class MeshControlManagerUI(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(MeshControlManagerUI, self).__init__(parent)
        self.setWindowTitle("Mesh Control Manager {}".format(APP_VERSION))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.setMinimumSize(340, 410)
        self.resize(370, 560)
        self.setSizeGripEnabled(True)
        self._updating_ui = False
        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(4, 4, 4, 4)

        menu_bar = QtWidgets.QMenuBar(self)
        help_menu = menu_bar.addMenu("Help")
        docs_action = QtWidgets.QAction("Online Documentation", self)
        docs_action.triggered.connect(_open_documentation)
        help_menu.addAction(docs_action)
        root.setMenuBar(menu_bar)

        # Status bar
        status_row = QtWidgets.QHBoxLayout()
        self._status_icon = QtWidgets.QLabel()
        self._status_icon.setFixedSize(12, 12)
        self._status_label = QtWidgets.QLabel("Not initialized")
        self._btn_select_overlay = QtWidgets.QPushButton()
        self._btn_select_overlay.setIcon(QtGui.QIcon(":/selectByObject.png"))
        self._btn_select_overlay.setFixedSize(24, 24)
        self._btn_select_overlay.setToolTip("Select the meshControlMode overlay node.")
        refresh_btn = QtWidgets.QPushButton()
        refresh_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.setToolTip("Refresh UI and repair the active viewport mode when tracked meshes exist.")
        self._btn_select_overlay.clicked.connect(self._on_select_overlay)
        refresh_btn.clicked.connect(self._on_refresh)
        status_row.addWidget(self._status_icon)
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        status_row.addWidget(self._btn_select_overlay)
        status_row.addWidget(refresh_btn)
        root.addLayout(status_row)

        # Separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        root.addWidget(line)

        body = QtWidgets.QVBoxLayout()
        body.setSpacing(4)
        body.setContentsMargins(0, 0, 0, 0)
        root.addLayout(body, 1)

        # Tracking list and actions
        tracking_group = QtWidgets.QGroupBox("Tracked Meshes")
        tracking_group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        tracking_layout = QtWidgets.QVBoxLayout(tracking_group)
        tracking_layout.setContentsMargins(6, 4, 6, 5)
        tracking_layout.setSpacing(4)

        self._list = _MeshListWidget()
        tracking_layout.addWidget(self._list, 1)

        btn_grid = QtWidgets.QGridLayout()
        btn_grid.setSpacing(3)

        self._btn_set    = QtWidgets.QPushButton("Track Selected")
        self._btn_add    = QtWidgets.QPushButton("Add Tracking")
        self._btn_rem    = QtWidgets.QPushButton("Remove")
        self._btn_sel    = QtWidgets.QPushButton("Select")
        self._btn_clear  = QtWidgets.QPushButton("Clear Tracking")
        self._btn_disable = QtWidgets.QPushButton("Disable")

        self._btn_set.setToolTip("Start tracking the current Maya mesh selection.")
        self._btn_add.setToolTip("Append selected Maya meshes to the tracked list.")
        self._btn_rem.setToolTip("Remove list-selected meshes from tracking.")
        self._btn_sel.setToolTip("Select list-selected meshes in the Maya viewport.")
        self._btn_clear.setToolTip("Stop tracking all meshes.")
        self._btn_disable.setToolTip("Turn off meshControlMode without deleting mesh metadata.")

        self._btn_clear.setObjectName("dangerBtn")
        self._btn_clear.setStyleSheet(
            "#dangerBtn { color: #d45; }"
            "#dangerBtn:hover { color: #f66; }"
        )

        btn_grid.addWidget(self._btn_set,   0, 0)
        btn_grid.addWidget(self._btn_add,   0, 1)
        btn_grid.addWidget(self._btn_rem,   1, 0)
        btn_grid.addWidget(self._btn_sel,   1, 1)
        btn_grid.addWidget(self._btn_clear, 2, 0)
        btn_grid.addWidget(self._btn_disable, 2, 1)

        tracking_layout.addLayout(btn_grid, 0)
        body.addWidget(tracking_group, 1)

        self._btn_set.clicked.connect(self._on_set)
        self._btn_add.clicked.connect(self._on_add)
        self._btn_rem.clicked.connect(self._on_remove)
        self._btn_sel.clicked.connect(self._on_select_in_scene)
        self._btn_clear.clicked.connect(self._on_clear)
        self._btn_disable.clicked.connect(self._on_disable)

        # Click target metadata
        target_group = QtWidgets.QGroupBox("Click Target")
        target_group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        target_layout = QtWidgets.QVBoxLayout(target_group)
        target_layout.setContentsMargins(6, 4, 6, 5)
        self._select_parent_cb = QtWidgets.QCheckBox("Select parent on click")
        self._select_parent_cb.setTristate(True)
        self._select_parent_cb.setToolTip(
            "When enabled on a tracked mesh, clicking its patch selects the parent transform.\n"
            "Default is off, so clicking selects the mesh transform.")
        target_layout.addWidget(self._select_parent_cb)
        body.addWidget(target_group, 0)
        self._select_parent_cb.stateChanged.connect(self._on_select_parent_changed)

        # Overlay display controls
        display_group = QtWidgets.QGroupBox("Overlay Display")
        display_group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        display_row = QtWidgets.QHBoxLayout(display_group)
        display_row.setContentsMargins(6, 4, 6, 5)
        self._xray_cb = QtWidgets.QCheckBox("X-Ray")
        self._wire_cb = QtWidgets.QCheckBox("Wire")
        self._marker_cb = QtWidgets.QCheckBox("Marker")
        self._readout_cb = QtWidgets.QCheckBox("Readout")
        self._xray_cb.setToolTip("Draw overlays in x-ray mode.")
        self._wire_cb.setToolTip("Draw overlay surfaces as wireframe.")
        self._marker_cb.setToolTip("Show the hover hit marker.")
        self._readout_cb.setToolTip("Show transform value readouts on overlay controls.")
        display_row.addWidget(self._xray_cb)
        display_row.addWidget(self._wire_cb)
        display_row.addWidget(self._marker_cb)
        display_row.addWidget(self._readout_cb)
        display_row.addStretch()
        body.addWidget(display_group, 0)
        self._xray_cb.stateChanged.connect(self._on_overlay_display_changed)
        self._wire_cb.stateChanged.connect(self._on_overlay_display_changed)
        self._marker_cb.stateChanged.connect(self._on_overlay_display_changed)
        self._readout_cb.stateChanged.connect(self._on_overlay_display_changed)

        # Creation helpers
        create_group = QtWidgets.QGroupBox("Build")
        create_group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        create_grid = QtWidgets.QGridLayout(create_group)
        create_grid.setContentsMargins(6, 4, 6, 5)
        create_grid.setSpacing(3)
        self._btn_vertex_wrap = QtWidgets.QPushButton("VertexWrap")
        self._btn_shape_baked = QtWidgets.QPushButton("ShapeControl Baked")
        self._btn_shape_live = QtWidgets.QPushButton("ShapeControl Live")
        self._btn_vertex_wrap.setToolTip("Select driver first, then driven patches. Creates only the vertexWrap deformer.")
        self._btn_shape_baked.setToolTip("Create a baked shapeControl from selected mesh/curve.")
        self._btn_shape_live.setToolTip("Create a live shapeControl connected to selected mesh/curve.")
        create_grid.addWidget(self._btn_vertex_wrap, 0, 0, 1, 2)
        create_grid.addWidget(self._btn_shape_baked, 1, 0)
        create_grid.addWidget(self._btn_shape_live, 1, 1)
        body.addWidget(create_group, 0)
        self._btn_vertex_wrap.clicked.connect(self._on_vertex_wrap_bind)
        self._btn_shape_baked.clicked.connect(lambda: self._on_shape_control_create(False))
        self._btn_shape_live.clicked.connect(lambda: self._on_shape_control_create(True))

        # Pin helpers
        pin_group = QtWidgets.QGroupBox("Pin")
        pin_group.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        pin_grid = QtWidgets.QGridLayout(pin_group)
        pin_grid.setContentsMargins(6, 4, 6, 5)
        pin_grid.setSpacing(3)
        self._btn_surface_pin = QtWidgets.QPushButton("Surface Pin")
        self._btn_surface_uv_pin = QtWidgets.QPushButton("Surface UV Pin")
        self._pin_maintain_offset_cb = QtWidgets.QCheckBox("Maintain offset")
        self._pin_maintain_offset_cb.setChecked(True)
        self._pin_inverse_cb = QtWidgets.QCheckBox("Inverse")
        self._pin_connect_combo = QtWidgets.QComboBox()
        self._pin_connect_combo.addItem("Matrix", "matrix")
        self._pin_connect_combo.addItem("Translate", "translate")
        self._btn_surface_pin.setToolTip("Select mesh first, then controls. Creates a surfacePin bind.")
        self._btn_surface_uv_pin.setToolTip("Select mesh first, then controls. Creates a UV-based surfaceUVPin bind.")
        self._pin_maintain_offset_cb.setToolTip("Keep each control's current world offset at bind time.")
        self._pin_inverse_cb.setToolTip("Cancel each control's own local TRS visually at bind time.")
        self._pin_connect_combo.setToolTip("Connect output matrix or translate-only output.")
        pin_grid.addWidget(self._btn_surface_pin, 0, 0)
        pin_grid.addWidget(self._btn_surface_uv_pin, 0, 1)
        pin_grid.addWidget(QtWidgets.QLabel("Surface Pin Output"), 1, 0)
        pin_grid.addWidget(self._pin_connect_combo, 1, 1)
        pin_grid.addWidget(self._pin_maintain_offset_cb, 2, 0)
        pin_grid.addWidget(self._pin_inverse_cb, 2, 1)
        body.addWidget(pin_group, 0)
        self._btn_surface_pin.clicked.connect(self._on_surface_pin_bind)
        self._btn_surface_uv_pin.clicked.connect(self._on_surface_uv_pin_bind)

        # Double-click list item: select in scene
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.itemSelectionChanged.connect(self._on_list_selection_changed)

        for button in self.findChildren(QtWidgets.QPushButton):
            if button.text():
                button.setMinimumHeight(23)

    # ------------------------------------------------------------------
    # State refresh
    # ------------------------------------------------------------------

    def _refresh(self):
        self._updating_ui = True
        try:
            self._cmd_mesh_mode = _command_exists("meshControlMode")
            self._cmd_vertex_wrap = _command_exists("vertexWrap")
            self._cmd_shape_create = _command_exists("shapeControlCreate")
            self._cmd_surface_pin = _command_exists("surfacePinBind")
            self._cmd_surface_uv_pin = _command_exists("surfaceUVPinBind")

            paths = _get_tracked_paths()
            self._list.populate(paths)

            exists = cmds.objExists(OVERLAY_SHAPE)
            count = len(paths)
            self._update_tracking_action_label(count)

            if not self._cmd_mesh_mode:
                self._status_label.setText("Plugin commands unavailable")
                self._set_status_color("#d45")
            elif not exists:
                self._status_label.setText("Not initialized")
                self._set_status_color("#888")
            elif count == 0:
                self._status_label.setText("Enabled - no meshes tracked")
                self._set_status_color("#fa0")
            else:
                noun = "mesh" if count == 1 else "meshes"
                self._status_label.setText("Active - {} {} tracked".format(count, noun))
                self._set_status_color("#4c4")

            self._xray_cb.setChecked(_get_overlay_bool("drawInXray", False))
            self._wire_cb.setChecked(_get_overlay_bool("drawWireframe", False))
            self._marker_cb.setChecked(_get_overlay_bool("drawMarker", True))
            self._readout_cb.setChecked(_get_overlay_bool("showTransformReadout", True))
        finally:
            self._updating_ui = False

        self._update_action_state()

    def _set_status_color(self, color):
        self._status_icon.setStyleSheet(
            "background: {}; border-radius: 6px;".format(color))

    def _update_tracking_action_label(self, tracked_count):
        if tracked_count > 0:
            self._btn_set.setText("Replace Tracking")
            self._btn_set.setToolTip(
                "Replace all currently tracked meshes with the current Maya selection.\n"
                "A confirmation is shown first.")
        else:
            self._btn_set.setText("Track Selected")
            self._btn_set.setToolTip("Start tracking the current Maya mesh selection.")

    def _update_action_state(self):
        mesh_cmd = getattr(self, "_cmd_mesh_mode", False)
        overlay_exists = cmds.objExists(OVERLAY_SHAPE)
        has_tracked_meshes = bool(self._list.all_paths())
        selected_rows = bool(self._list.selected_paths())

        self._btn_set.setEnabled(mesh_cmd)
        self._btn_add.setEnabled(mesh_cmd)
        self._btn_clear.setEnabled(mesh_cmd and overlay_exists)
        self._btn_disable.setEnabled(mesh_cmd and overlay_exists)
        self._btn_select_overlay.setEnabled(mesh_cmd and overlay_exists and has_tracked_meshes)
        self._btn_rem.setEnabled(mesh_cmd and selected_rows)
        self._btn_sel.setEnabled(selected_rows)

        overlay_enabled = mesh_cmd and overlay_exists
        self._xray_cb.setEnabled(overlay_enabled)
        self._wire_cb.setEnabled(overlay_enabled)
        self._marker_cb.setEnabled(overlay_enabled)
        self._readout_cb.setEnabled(overlay_enabled)

        self._btn_vertex_wrap.setEnabled(getattr(self, "_cmd_vertex_wrap", False))
        self._btn_shape_baked.setEnabled(getattr(self, "_cmd_shape_create", False))
        self._btn_shape_live.setEnabled(getattr(self, "_cmd_shape_create", False))

        self._btn_surface_pin.setEnabled(getattr(self, "_cmd_surface_pin", False))
        self._btn_surface_uv_pin.setEnabled(getattr(self, "_cmd_surface_uv_pin", False))
        self._pin_maintain_offset_cb.setEnabled(
            getattr(self, "_cmd_surface_pin", False) or getattr(self, "_cmd_surface_uv_pin", False))
        self._pin_inverse_cb.setEnabled(
            getattr(self, "_cmd_surface_pin", False) or getattr(self, "_cmd_surface_uv_pin", False))
        self._pin_connect_combo.setEnabled(getattr(self, "_cmd_surface_pin", False))

        self._update_select_parent_state()

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_refresh(self):
        paths = _get_tracked_paths()
        if paths and _command_exists("meshControlMode"):
            try:
                cmds.meshControlMode(reactivate=True)
            except Exception as e:
                cmds.warning(str(e))
        self._refresh()

    def _on_select_overlay(self):
        try:
            cmds.meshControlMode(select=True)
        except Exception as e:
            cmds.warning(str(e))

    def _on_set(self):
        if not self._has_mesh_selected():
            return
        paths = _get_tracked_paths()
        if paths:
            noun = "mesh" if len(paths) == 1 else "meshes"
            confirm = QtWidgets.QMessageBox.question(
                self, "Replace Tracking",
                "Replace {} currently tracked {} with the current Maya selection?".format(len(paths), noun),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if confirm != QtWidgets.QMessageBox.Yes:
                return
        try:
            cmds.meshControlMode(enable=True)
        except Exception as e:
            cmds.warning(str(e))
        self._refresh()

    def _on_add(self):
        if not self._has_mesh_selected():
            return
        try:
            cmds.meshControlMode(append=True)
        except Exception as e:
            cmds.warning(str(e))
        self._refresh()

    def _on_remove(self):
        paths = self._list.selected_paths()
        if not paths:
            cmds.warning("Select mesh(es) in the list to remove.")
            return
        try:
            cmds.meshControlMode(remove=True, meshPaths=",".join(paths))
        except Exception as e:
            cmds.warning(str(e))
        self._refresh()

    def _on_select_in_scene(self):
        paths = self._list.selected_paths()
        if not paths:
            return
        try:
            _select_mesh_transforms(paths)
        except Exception as e:
            cmds.warning("Select failed: " + str(e))

    def _on_clear(self):
        confirm = QtWidgets.QMessageBox.question(
            self, "Clear All",
            "Remove all tracked meshes?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return
        try:
            cmds.meshControlMode(clear=True)
        except Exception as e:
            cmds.warning(str(e))
        self._refresh()

    def _on_disable(self):
        try:
            cmds.meshControlMode(enable=False)
        except Exception as e:
            cmds.warning(str(e))
        self._refresh()

    def _on_select_parent_changed(self, state):
        if self._updating_ui:
            return
        if state == int(QtCore.Qt.PartiallyChecked):
            return
        paths = self._list.selected_paths()
        if not paths:
            return
        try:
            _set_select_parent(paths, state == int(QtCore.Qt.Checked))
        except Exception as e:
            cmds.warning("Could not update meshControlSelectParent: " + str(e))
        self._update_select_parent_state()

    def _on_overlay_display_changed(self):
        if self._updating_ui:
            return
        try:
            _set_overlay_bool("drawInXray", self._xray_cb.isChecked())
            _set_overlay_bool("drawWireframe", self._wire_cb.isChecked())
            _set_overlay_bool("drawMarker", self._marker_cb.isChecked(), selected_too=False)
            _set_overlay_bool("showTransformReadout", self._readout_cb.isChecked())
            cmds.refresh(force=True)
        except Exception as e:
            cmds.warning("Could not update overlay display: " + str(e))

    def _on_vertex_wrap_bind(self):
        selection = cmds.ls(selection=True, long=True) or []
        if len(selection) < 2:
            cmds.warning("Select driver first, then one or more driven patches.")
            return
        name = _short_name(selection[0]).split(":")[-1] + "_vertexWrap"
        try:
            cmds.vertexWrap(name=name)
        except Exception as e:
            cmds.warning(str(e))
        self._refresh()

    def _on_shape_control_create(self, live):
        selection = cmds.ls(selection=True, long=True) or []
        if not selection:
            cmds.warning("Select a mesh or curve first.")
            return
        try:
            cmds.shapeControlCreate(live=bool(live))
        except Exception as e:
            cmds.warning(str(e))
        self._refresh()

    def _on_surface_pin_bind(self):
        if not self._has_pin_selection():
            return
        kwargs = {
            "inverse": self._pin_inverse_cb.isChecked(),
            "connect": self._pin_connect_combo.currentData(),
        }
        if self._pin_maintain_offset_cb.isChecked():
            kwargs["maintainOffset"] = True
        try:
            cmds.surfacePinBind(**kwargs)
        except Exception as e:
            cmds.warning(str(e))

    def _on_surface_uv_pin_bind(self):
        if not self._has_pin_selection():
            return
        kwargs = {
            "inverse": self._pin_inverse_cb.isChecked(),
        }
        if self._pin_maintain_offset_cb.isChecked():
            kwargs["maintainOffset"] = True
        try:
            cmds.surfaceUVPinBind(**kwargs)
        except Exception as e:
            cmds.warning(str(e))

    def _on_list_selection_changed(self):
        self._update_action_state()

    def _on_item_double_clicked(self, item):
        path = item.data(QtCore.Qt.UserRole)
        try:
            _select_mesh_transforms([path])
        except Exception as e:
            cmds.warning("Select failed: " + str(e))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _update_select_parent_state(self):
        if not hasattr(self, "_select_parent_cb"):
            return

        paths = self._list.selected_paths()
        self._updating_ui = True
        try:
            can_edit = bool(paths) and getattr(self, "_cmd_mesh_mode", False)
            self._select_parent_cb.setEnabled(can_edit)
            self._select_parent_cb.setTristate(len(paths) > 1)
            if not paths:
                self._select_parent_cb.setCheckState(QtCore.Qt.Unchecked)
                self._select_parent_cb.setToolTip("Select tracked mesh rows to edit click target metadata.")
                return
            if not can_edit:
                self._select_parent_cb.setCheckState(QtCore.Qt.Unchecked)
                self._select_parent_cb.setToolTip("Load the plugin commands to edit click target metadata.")
                return

            values = [_get_select_parent(path) for path in paths]
            if all(values):
                state = QtCore.Qt.Checked
            elif any(values):
                state = QtCore.Qt.PartiallyChecked
            else:
                state = QtCore.Qt.Unchecked
            self._select_parent_cb.setCheckState(state)
            self._select_parent_cb.setToolTip(
                "When enabled on a tracked mesh, clicking its patch selects the parent transform.\n"
                "Default is off, so clicking selects the mesh transform.")
        finally:
            self._updating_ui = False

    def _has_mesh_selected(self):
        meshes = cmds.ls(selection=True, dag=True, type="mesh") or []
        if not meshes:
            cmds.warning("Select a mesh in the viewport first.")
            return False
        return True

    def _has_pin_selection(self):
        selection = cmds.ls(selection=True, long=True) or []
        if len(selection) < 2:
            cmds.warning("Select mesh first, then one or more controls.")
            return False
        if not _mesh_transform(selection[0]):
            cmds.warning("First selected object must be a mesh or mesh transform.")
            return False
        return True


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_window = None


def show():
    """Open or raise the Mesh Control Manager window."""
    global _window

    from maya import OpenMayaUI as omui
    from shiboken2 import wrapInstance
    ptr = omui.MQtUtil.mainWindow()
    maya_main = wrapInstance(int(ptr), QtWidgets.QWidget)

    # Close any existing window, including orphans left by module reloads.
    for widget in maya_main.findChildren(MeshControlManagerUI):
        try:
            widget.close()
            widget.deleteLater()
        except Exception:
            pass

    if _window is not None:
        try:
            _window.close()
            _window.deleteLater()
        except Exception:
            pass

    _window = MeshControlManagerUI(maya_main)
    _window.show()
    _window.raise_()
    _window.activateWindow()

    # If the scene has tracked meshes but the mode isn't active yet
    # (e.g. just opened Maya), reactivate automatically.
    if _get_tracked_paths() and _command_exists("meshControlMode"):
        try:
            cmds.meshControlMode(reactivate=True)
            _window._refresh()
        except Exception:
            pass
