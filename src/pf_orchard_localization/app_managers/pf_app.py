#!/usr/bin/env python3
import sys
from dataclasses import fields
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QWidget
from PyQt6.QtGui import QSurfaceFormat
from ..custom_widgets import (PfMainWindow, PfControlButtons, PfStartLocationControls, PfCheckBoxes,
                              Console, ImageDisplay, PfModeSelector, ImageBrowsingControls, TreatingPFPlotter,
                              DataFileControls, ImageNumberLabel, ImageDelaySlider, CachedDataCreator,
                              PfChangeParametersButton, PfTestControls, PfQueueSizeLabel, RosConnectButton,
                              CalibrationDataControls)
from ..utils.parameters import ParametersPf, ParametersBagData, ParametersCachedData, ParametersLiveData
from ..pf_engine import PFEngine
from map_data_tools import MapData
import logging
from ..trunk_data_connection import TrunkDataConnection, TrunkDataConnectionCachedData
from ..app_modes import PfMode, PfModeCached, PfModeCachedTests, PlaybackMode, PfLiveMode, PfModeSaveCalibrationData
import os
from functools import partial
import time
import copy


class PfAppBase(PfMainWindow):
    
    def __init__(self, config_file_path: str, logging_level=logging.DEBUG):
        """
        Main application class for the particle filter localization app

        Args:
            config_file_path (str): Path to the configuration file
            logging_level: Logging level for the app
        """
        super().__init__()

        # Initialize parameters
        self.init_data_parameters(config_file_path)
        self.parameters_data.load_from_yaml(config_file_path)
        self.parameters_pf = ParametersPf()
        self.parameters_pf.load_from_yaml(self.parameters_data.pf_config_file_path)

        # Get map data
        self.map_data = MapData(map_data_path=self.parameters_data.map_data_path, move_origin=True, origin_offset=(5, 5))

        # Initialize the particle filter engine
        self.pf_engine = PFEngine(self.map_data)

        self.init_widgets()
        self.draw_ui()

        self.current_msg = None
        self.active_mode = None

        self.connect_app_to_ui()

        self.setup_trunk_data_connection()

        self.init_loaded_data()

        self.modes = []

        self.init_modes()

        self.mode_selector.set_modes(self.modes)

        self.mode_changed()

    def init_data_parameters(self, config_file_path: str):
        """
        Initialize the data parameters

        Args:
            config_file_path (str): Path to the configuration file for the app data parameters
        """
        self.parameters_data = None

    def init_loaded_data(self):
        """Initialize the data manager and load the first image"""
        pass
        
    #     # self.data_manager = None

    #     # # Select the first item in the combo box
    #     # self.open_data_file()

    #     # if self.parameters_data.initial_data_time is not None and self.data_manager is not None:
    #     #     self.data_file_time_line.set_time_line(float(self.parameters_data.initial_data_time))
    #     #     self.data_manager.set_time_stamp(float(self.parameters_data.initial_data_time))
        # self.data_file_controls.open_data_file()

    def init_modes(self):
        """Initialize the modes for the app"""
        pass
    
    def draw_ui(self):
        """Draw the user interface"""
        pass

    def init_widgets(self):
        """Initialize all the widgets used in the app"""
        # Set up the main window
        self.setWindowTitle("Orchard Particle Filter Localization App")
        self.init_window_display_settings()

        self.widget_list = []

        self.main_layout = QHBoxLayout()

        # Setup widgets shared by all the app types
        self.start_location_controls = PfStartLocationControls(self)
        self.control_buttons = PfControlButtons(self)
        self.change_parameters_button = PfChangeParametersButton(self)
        self.mode_selector = PfModeSelector()
        self.image_display = ImageDisplay(num_camera_feeds=1, scale_factor=1.0)
        self.image_browsing_controls = ImageBrowsingControls()
        self.console = Console()

        # Setup the checkboxes
        self.checkboxes = PfCheckBoxes()
        self.checkboxes.all_checkbox_info.append(
            ["include_width_checkbox", "Use Width in Weight Calculation", self.parameters_pf.include_width])
        self.checkboxes.all_checkbox_info.append(
            ["stop_when_converged_checkbox", "Stop When Converged", self.parameters_pf.stop_when_converged])
        self.checkboxes.all_checkbox_info.append(
            ["show_pre_filtered_segmentation_checkbox", "Show Pre-Filtered Segmentation", False])
        self.checkboxes.all_checkbox_info.append(
            ["show_rgb_image_checkbox", "Show Original Image", False])
        self.checkboxes.init_checkboxes()

        self.plotter = TreatingPFPlotter(self.map_data)

        # Set the central widget of the app
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        central_widget.setLayout(self.main_layout)

        # Setup the widgets unique to the app types
        self.init_widgets_unique()

        # Add the widgets to the list of all widgets
        # Note that ui_layout always needs to be at the end of this list or bugs will occur, or really, it needs to have
        # top level widgets added to it last
        self.widget_list += [self.start_location_controls, self.checkboxes, self.change_parameters_button,
                            self.mode_selector, self.control_buttons, self.image_display, self.console, self.plotter,]

    def init_widgets_unique(self):
        """Initialize the widgets unique to the app type"""
        pass

    def connect_app_to_ui(self):
        """Connect the UI elements to the app functions"""

        self.control_buttons.reset_button.clicked.connect(lambda x: self.reset_pf(use_ui_parameters=True))

        self.plotter.plot_widget.clicked.connect(self.start_location_controls.set_start_location_from_plot_click)

        self.checkboxes.include_width_checkbox.stateChanged.connect(self.include_width_changed)
        self.checkboxes.show_rgb_image_checkbox.stateChanged.connect(self.image_display_checkbox_changed)
        self.checkboxes.show_pre_filtered_segmentation_checkbox.stateChanged.connect(self.image_display_checkbox_changed)
        self.checkboxes.stop_when_converged_checkbox.stateChanged.connect(self.stop_when_converged_changed)

        self.mode_selector.mode_selector.currentIndexChanged.connect(self.mode_changed)

        self.connect_app_to_ui_unique()

    def connect_app_to_ui_unique(self):
        """Connect the app functions unique to the app type"""
        pass

    def setup_trunk_data_connection(self):
        """Setup the object that connects the app to the trunk segmenter and analyzer"""
        pass

    def image_display_checkbox_changed(self):
        """Change the camera feed display based on the checkboxes selected, called when one of the checkboxes that
        changes the image display is changed."""

        show_rgb_image = self.checkboxes.show_rgb_image_checkbox.isChecked()
        show_pre_filtered_segmentation = self.checkboxes.show_pre_filtered_segmentation_checkbox.isChecked()

        # Number of camera feeds needed
        num_camera_feeds = 1 + show_rgb_image + show_pre_filtered_segmentation

        # Check if the image display is already in the layout, if so, remove it. It returns -1 if it is not in the layout
        image_display_index = self.ui_layout.indexOf(self.image_display)
        if image_display_index != -1:
            self.ui_layout.removeWidget(self.image_display)

        # Delete and remove the image display widget and object and create a new one with the new number of camera feeds
        self.widget_list.remove(self.image_display)
        self.image_display.deleteLater()
        self.image_display = ImageDisplay(num_camera_feeds=num_camera_feeds, scale_factor=self.parameters_data.image_display_scale)
        self.widget_list.insert(0, self.image_display)

        # If the image display was in the layout, add it back in where it was
        if image_display_index != -1:
            self.ui_layout.insertWidget(image_display_index, self.image_display)

        # Tell the trunk_data_connection object where to display the images
        display_num = 0
        if show_rgb_image:
            self.trunk_data_connection.original_image_display_func = partial(self.image_display.load_image, img_num=display_num)
            display_num += 1
        else:
            self.trunk_data_connection.original_image_display_func = None
        if show_pre_filtered_segmentation:
            self.trunk_data_connection.pre_filtered_segmentation_display_func = partial(self.image_display.load_image, img_num=display_num)
            display_num += 1
        else:
            self.trunk_data_connection.pre_filtered_segmentation_display_func = None
        self.trunk_data_connection.seg_image_display_func = partial(self.image_display.load_image, img_num=display_num)

        # Update the image display with the current image if there is one
        if self.current_msg is not None:
            self.trunk_data_connection.get_trunk_data(self.current_msg)

    def include_width_changed(self):
        """Change the include width parameter in the particle filter parameters according to the checkbox"""
        self.parameters_pf.include_width = self.checkboxes.include_width_checkbox.isChecked()

    def stop_when_converged_changed(self):
        """Change the stop when converged parameter in the particle filter parameters according to the checkbox"""
        self.parameters_pf.stop_when_converged = self.checkboxes.stop_when_converged_checkbox.isChecked()
    
    def hide_all_widgets(self):
        """Disable all the widgets in the app"""
        # for widget in self.widget_list:
        #     if widget is not None:
        #         widget.setParent(None)
        for widget in self.widget_list:
            if widget is not None:
                widget.hide()           
                
    def mode_changed(self):
        """Change the active mode based on the mode selector"""

        # Find the active mode and deactivate it
        for mode in self.modes:
            if mode.mode_active:
                mode.deactivate_mode()

        self.hide_all_widgets()

        # Find the new active mode and activate it
        for mode in self.modes:
            if mode.mode_name == self.mode_selector.mode:
                mode.activate_mode()
                self.active_mode = mode
                break
        
        # add the mode names back to the mode selector
        # self.mode_selector.set_modes(self.modes)
        
    # def data_file_time_line_edited(self):
    #     """Change the time the data file is at based on a time entered in the time line edit box by the user"""

    #     time_stamp = self.data_file_time_line.data_file_time_line.text()

    #     # Check if the value entered is a number
    #     try:
    #         time_stamp = float(time_stamp)
    #     except ValueError:
    #         self.print_message("Invalid time stamp")
    #         return

    #     # Set the time stamp in the data manager and get the current message
    #     message, self.current_msg = self.data_manager.set_time_stamp(time_stamp)

    #     self.print_message(message)

    #     # Update the app with the message from the new time stamp and set the time line to match the exact time stamp of the message
    #     if self.current_msg is not None:
    #         self.trunk_data_connection.get_trunk_data(self.current_msg)
    #         self.data_file_time_line.set_time_line(self.data_manager.current_data_file_time_stamp)

    #     self.image_number_label.set_img_number_label(self.data_manager.current_img_position,
    #                                                       self.data_manager.num_img_msgs)

    # def open_data_file(self, data_file_name: str = None, load_first_image: bool = True):
    #     """
    #     Open a data file using a data manager object

    #     Args:
    #         data_file_name (str): Name of the data file to open
    #         load_first_image (bool): Whether to load the first image in the data file
    #     """
    #     # If no data file name is given, use the current data file selection
    #     if data_file_name is None:
    #         data_file_name = self.data_file_controls.current_data_file_selection

    #     self.data_file_controls.set_opening()

    #     data_file_path = self.data_file_controls.data_file_dir + data_file_name

    #     valid, message = self.check_data_file_is_valid(data_file_path)
        
    #     if not valid:
    #         self.data_file_controls.set_opened(message)
    #         return
        
    #     if data_file_path.endswith(".json"):
    #         data_manager = CachedDataLoader(data_file_path)
    #     else:
    #         data_manager = Bag2DataLoader(data_file_path, self.parameters_data.depth_topic, self.parameters_data.rgb_topic, self.parameters_data.odom_topic)

    #     if data_manager.num_img_msgs == 0:
    #         self.data_file_open_button.set_opened("No images found in data file, check topic names")
    #         return

    #     self.data_file_time_line.set_time_line(data_manager.current_data_file_time_stamp)

    #     self.data_manager = data_manager

    #     msg = ["Opened bag file: " + data_file_name,]
    #     msg.append("Number of Odom messages: " + str(self.data_manager.num_odom_msgs))
    #     msg.append("Number of images: " + str(self.data_manager.num_img_msgs))

    #     self.data_file_controls.set_opened(msg)

    #     if load_first_image:
    #         self.current_msg = self.data_manager.get_next_img_msg()
    #         self.trunk_data_connection.get_trunk_data(self.current_msg)
    #         self.image_number_label.set_img_number_label(self.data_manager.current_img_position,
    #                                                      self.data_manager.num_img_msgs)
            
    # def check_data_file_is_valid(self, data_file_path: str):
    #     """Check if a data file is valid

    #     Args:
    #         data_file_name (str): Name of the data file to check
    #     """
    #     if not os.path.isfile(data_file_path) and not os.path.isdir(data_file_path):
    #         return False, "Invalid file name"
    #     elif data_file_path.endswith(".json") and not self.using_cached_data:
    #         return False, "Invalid file type, not using cached data"
    #     elif data_file_path.endswith(".json") and self.using_cached_data:
    #         return True, "Valid file"
    #     elif os.path.isdir(data_file_path):
    #         files = os.listdir(data_file_path)
    #         if len(files) == 2:
    #             file_endings = [file.split(".")[-1] for file in files]
    #             if "yaml" in file_endings and "db3" in file_endings:
    #                 return True, "Valid file"
    #     else:
    #         return False, "Invalid file"
    
    # @pyqtSlot()
    # def load_next_data_file(self, load_first_image=True):
    #     """Load the next data file in the list of data files.

    #     Args:
    #         load_first_image (bool): Whether to load the first image in the new data file
    #     """
    #     current_data_file_name = self.data_manager.current_data_file_name

    #     if self.using_cached_data:
    #         self.print_message("Cannot load next data file when using cached data")
    #         return False

    #     next_data_file_name = self.data_file_controls.get_next_data_file_name(current_data_file_name)

    #     if next_data_file_name is None:
    #         self.print_message("Reached the end of the data files")
    #         return False

    #     self.open_data_file(next_data_file_name, load_first_image)

    #     return True, self.data_manager

    @pyqtSlot(bool)
    def reset_pf(self, use_ui_parameters=True):
        """Reset the particle filter.

        Args:
            use_ui_parameters (bool): Whether to use the parameters set in the UI or the parameters set in the app
        """
        if use_ui_parameters:
            self.start_location_controls.get_parameters()
        else:
            self.start_location_controls.set_parameters()

        self.pf_engine.reset_pf(self.parameters_pf)

        self.reset_gui()

    def reset_gui(self):
        """Reset the particle filter elements in the GUI"""

        self.control_buttons.set_num_particles(self.pf_engine.particles.shape[0])
        self.plotter.update_particles(self.pf_engine.downsample_particles())
        self.plotter.update_position_estimate(None)

    def get_pf_active(self):
        """Get whether the particle filter is currently active"""

        if self.active_mode is not None:
            if hasattr(self.active_mode, "pf_continuous_active"):
                return self.active_mode.pf_continuous_active

    def get_pf_parameters(self):
        """Get the particle filter parameters"""

        return self.parameters_pf

    def set_pf_parameters(self, parameters: ParametersPf):
        """Set the particle filter parameters

        Args:
            parameters (ParametersPf): Particle filter parameters
        """

        if self.get_pf_active():
            self.print_message("Cannot change parameters while the particle filter is running")
            return False
        self.parameters_pf = parameters
        return True

    @pyqtSlot(str)
    def print_message(self, message: str):
        """Print a message to the console

        Args:
            message (str): Message to print
        """

        if isinstance(message, list):
            for msg in message:
                self.console(msg)
        else:
            self.console(message)

    def display_pf_settings(self):
        """Display the current particle filter settings"""

        for field in fields(self.parameters_pf):
            value = getattr(self.parameters_pf, field.name)
            self.print_message(field.name + ": " + str(value))

    def closeEvent(self, event):
        for mode in self.modes:
            if mode.mode_active:
                mode.shutdown_hook()

        event.accept()

class PfAppBags(PfAppBase):
    def __init__(self, config_file_path, logging_level=logging.DEBUG):
        self.using_cached_data = False
        super().__init__(config_file_path, logging_level=logging_level)


    def init_data_parameters(self, config_file_path):
        self.parameters_data = ParametersBagData()
    
    def init_loaded_data(self):
        self.data_file_controls.open_data_file()

    def setup_trunk_data_connection(self):
        self.trunk_data_connection = TrunkDataConnection(self.parameters_data.width_estimation_config_file_path)
        self.image_display_checkbox_changed()
        self.data_file_controls.set_image_display.connect(self.trunk_data_connection.get_trunk_data)
        
    def init_widgets_unique(self):
        self.image_browsing_controls = ImageBrowsingControls()
        self.data_file_controls = DataFileControls(self.parameters_data)
        self.image_number_label = ImageNumberLabel()
        self.image_delay_slider = ImageDelaySlider()
        self.cached_data_creator = CachedDataCreator(self)
        self.save_calibration_data_controls = CalibrationDataControls(self)

        self.widget_list += [self.image_browsing_controls, self.data_file_controls,
                                self.image_number_label, self.image_delay_slider, self.cached_data_creator, self.save_calibration_data_controls]

    def draw_ui(self):
        mode_change_button_layout = QHBoxLayout()
        mode_change_button_layout.addWidget(self.mode_selector)
        mode_change_button_layout.addWidget(self.change_parameters_button)

        control_layout = QHBoxLayout()
        control_layout.addWidget(self.control_buttons)
        control_layout.addWidget(self.image_delay_slider)

        self.ui_layout = QVBoxLayout()
        self.ui_layout.addLayout(mode_change_button_layout)
        self.ui_layout.addWidget(self.checkboxes)
        self.ui_layout.addWidget(self.start_location_controls)
        self.ui_layout.addLayout(control_layout)
        self.ui_layout.addWidget(self.image_display)
        self.ui_layout.addWidget(self.image_number_label)
        self.ui_layout.addWidget(self.image_browsing_controls)
        self.ui_layout.addWidget(self.data_file_controls)
        self.ui_layout.addWidget(self.cached_data_creator)
        self.ui_layout.addWidget(self.save_calibration_data_controls)
        self.ui_layout.addWidget(self.console)
        
        self.main_layout.addLayout(self.ui_layout)
        self.main_layout.addWidget(self.plotter)
        
    def connect_app_to_ui_unique(self):
        self.data_file_controls.data_file_controls_message.connect(self.print_message)
        self.data_file_controls.reset_pf.connect(self.reset_pf)
        self.data_file_controls.set_img_number_label.connect(self.image_number_label.set_img_number_label)        

    def init_modes(self):
        self.pf_mode = PfMode(self)
        self.modes.append(self.pf_mode)
        self.playback_mode = PlaybackMode(self)
        self.modes.append(self.playback_mode)
        self.get_calibration_data_mode = PfModeSaveCalibrationData(self)
        self.modes.append(self.get_calibration_data_mode)

class PfAppCached(PfAppBase):
    def __init__(self, config_file_path, logging_level=logging.DEBUG):
        self.using_cached_data = True
        super().__init__(config_file_path, logging_level=logging_level)
        
        # check if it's a file
        if self.parameters_data.test_start_info_path is None:
            raise FileNotFoundError("No test_start_info_path given in config file")           
        if not os.path.isfile(self.parameters_data.test_start_info_path):
            raise FileNotFoundError("Invalid test_start_info_path given in config file")
            

    def init_data_parameters(self, config_file_path):
        self.parameters_data = ParametersCachedData()
    
    def init_loaded_data(self):
        self.data_file_controls.open_data_file()

    def setup_trunk_data_connection(self):
        self.trunk_data_connection = TrunkDataConnectionCachedData(self.parameters_data.cached_image_dir,
                                                                   self.image_display.load_image)
        
        self.data_file_controls.set_image_display.connect(self.trunk_data_connection.get_trunk_data)

    def init_widgets_unique(self):
        self.image_browsing_controls = ImageBrowsingControls()
        self.data_file_controls = DataFileControls(self.parameters_data, using_cached_data=True)
        self.image_number_label = ImageNumberLabel()
        self.image_delay_slider = ImageDelaySlider()
        self.cached_data_creator = CachedDataCreator(self)
        self.pf_test_controls = PfTestControls(self)

        self.widget_list += [self.image_browsing_controls, self.data_file_controls, self.image_number_label,
                             self.image_delay_slider, self.cached_data_creator, self.pf_test_controls]
    
    def draw_ui(self):
        mode_change_button_layout = QHBoxLayout()
        mode_change_button_layout.addWidget(self.mode_selector)
        mode_change_button_layout.addWidget(self.change_parameters_button)

        control_layout = QHBoxLayout()
        control_layout.addWidget(self.control_buttons)
        control_layout.addWidget(self.image_delay_slider)

        self.ui_layout = QVBoxLayout()
        
        self.ui_layout.addLayout(mode_change_button_layout)
        self.ui_layout.addWidget(self.checkboxes)
        self.ui_layout.addWidget(self.start_location_controls)
        self.ui_layout.addLayout(control_layout)
        self.ui_layout.addWidget(self.image_display)
        self.ui_layout.addWidget(self.image_number_label)
        self.ui_layout.addWidget(self.image_browsing_controls)
        self.ui_layout.addWidget(self.data_file_controls)
        self.ui_layout.addWidget(self.cached_data_creator)
        self.ui_layout.addWidget(self.pf_test_controls)
        self.ui_layout.addWidget(self.console)
        
        self.main_layout.addLayout(self.ui_layout)
        self.main_layout.addWidget(self.plotter)
    
    def connect_app_to_ui_unique(self):
        self.data_file_controls.data_file_controls_message.connect(self.print_message)
        self.data_file_controls.reset_pf.connect(self.reset_pf)
        self.data_file_controls.set_img_number_label.connect(self.image_number_label.set_img_number_label)   
        
    def init_modes(self):
        self.pf_tests_mode = PfModeCachedTests(self)
        self.modes.append(self.pf_tests_mode)
        
        self.pf_mode = PfModeCached(self)
        self.modes.append(self.pf_mode)
        
        
        self.playback_mode = PlaybackMode(self)
        self.modes.append(self.playback_mode)

    def image_display_checkbox_changed(self):
        self.print_message("Cannot change image display settings when using cached data")
        pass



class PfAppLive(PfAppBase):
    def __init__(self, config_file_path, logging_level=logging.DEBUG):
        super().__init__(config_file_path, logging_level=logging_level)

    def init_data_parameters(self, config_file_path):
        self.parameters_data = ParametersLiveData()

    def setup_trunk_data_connection(self):
        self.trunk_data_connection = TrunkDataConnection(self.parameters_data.width_estimation_config_file_path)
        self.image_display_checkbox_changed()

    def init_widgets_unique(self):
        self.queue_size_label = PfQueueSizeLabel()
        self.ros_connect_button = RosConnectButton()

        self.widget_list += [self.queue_size_label, self.ros_connect_button]
    
    def draw_ui(self):
        mode_change_button_layout = QHBoxLayout()
        mode_change_button_layout.addWidget(self.mode_selector)
        mode_change_button_layout.addWidget(self.change_parameters_button)

        self.ui_layout = QVBoxLayout()
        
        self.ui_layout.addLayout(mode_change_button_layout)
        self.ui_layout.addWidget(self.checkboxes)
        self.ui_layout.addWidget(self.start_location_controls)
        self.ui_layout.addWidget(self.control_buttons)
        self.ui_layout.addWidget(self.ros_connect_button)
        self.ui_layout.addWidget(self.queue_size_label)
        self.ui_layout.addWidget(self.image_display)
        self.ui_layout.addWidget(self.image_browsing_controls)
        self.ui_layout.addWidget(self.console)
        
        self.main_layout.addLayout(self.ui_layout)
        self.main_layout.addWidget(self.plotter)
    

    def init_modes(self):
        self.pf_live_mode = PfLiveMode(self)
        self.modes.append(self.pf_live_mode)

    def init_loaded_data(self):
        pass

if __name__ == "__main__":
    pf_app_bag_config_file_path = "/home/jostan/OneDrive/Docs/Grad_school/Research/code_projects/pf_orchard_localization/config/parameters_pf_app_bags.yaml"
    app = QApplication(sys.argv)

    pf_bag_app = PfAppBags(pf_app_bag_config_file_path)
    pf_bag_app.show()

    sys.exit(app.exec_())





