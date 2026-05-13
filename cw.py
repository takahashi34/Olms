from time import sleep
import numpy as np
from numpy import append, zeros, arange, logspace, log10, size
import os
import shutil
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import Label, Entry, Button, LabelFrame, OptionMenu, Radiobutton, StringVar, IntVar, DISABLED, NORMAL, font
from dataAnal import export_to_origin

from instruments import init_keithley, init_thermopile, read_light, init_detector
import pyvisa

# Import Browse button functions
from Browse_buttons import browse_plot_file, browse_txt_file
# Import Oscilloscope scaling and impedance
from Oscilloscope_Scaling import incrOscVertScale, channelImpedance
# Import live plotting
from live_plot import LivePlotLIV
# Import configuration manager
from config_manager import add_config_buttons

rm = pyvisa.ResourceManager()

class LDC3724B_TEC:
    def __init__(self, rm, address):
        self.inst = rm.open_resource(address)

    def set_temperature(self, temp_c):
        self.inst.write(f"TEC:T {temp_c}")

    def get_temperature(self):
        return float(self.inst.query("TEC:T?").strip())

    def set_gain(self, gain):
        self.inst.write(f"TEC:GAIN {gain}")

    def output_on(self):
        self.inst.write("TEC:OUT 1")

    def output_off(self):
        self.inst.write("TEC:OUT 0")

    def output_state(self):
        return self.inst.query("TEC:OUT?").strip() == "1"

    def close(self):
        self.output_off()
        self.inst.close()


class CW_LIV():


    """
    Function referenced when: "Start" button is pushed and oscilloscope mode is selected.
    Description: Runs an IV sweep using the various input parameters in the main application window
    such as: start voltage, stop voltage, step size, etc.
    """

    def init_tec(self):
        if not hasattr(self, 'tec'):
            self.tec = LDC3724B_TEC(rm, self.tec_address.get())

    def set_tec_temp(self):
        self.init_tec()
        temp = float(self.tec_temp_entry.get())
        self.tec.set_temperature(temp)
        self.tec.output_on()

    def toggle_tec(self):
        self.init_tec()
        if self.tec.output_state():
            self.tec.output_off()
        else:
            self.tec.output_on()

    def update_tec_readback(self):
        if hasattr(self, 'tec'):
            try:
                t = self.tec.get_temperature()
                self.tec_status.config(text=f'Current: {t:.2f} °C')
            except Exception:
                self.tec_status.config(text='TEC read error')

        self.master.after(1000, self.update_tec_readback)



    def build_tec_frame(self):
        self.tecFrame = LabelFrame(self.devFrame1, text='LDC-3724B TEC')
        self.tecFrame.grid(column=1, row=2, sticky='N', pady=(5, 0))

        Label(self.tecFrame, text='TEC address').grid(row=0, column=0, sticky='W')
        self.tec_address = StringVar()
        self.tec_address.set('Select...')

        addresses = list(rm.list_resources())
        OptionMenu(self.tecFrame, self.tec_address, *addresses).grid(row=0, column=1)

        Label(self.tecFrame, text='Temp. to Set (°C)').grid(row=1, column=0, sticky='W')
        self.tec_temp_entry = Entry(self.tecFrame, width=6)
        self.tec_temp_entry.grid(row=1, column=1)

        self.tec_status = Label(self.tecFrame, text='Current: --- °C')
        self.tec_status.grid(row=2, column=0, columnspan=2)

        Button(self.tecFrame, text='Send Temp.', command=self.set_tec_temp).grid(row=3, column=0)
        Button(self.tecFrame, text='Toggle Output', command=self.toggle_tec).grid(row=3, column=1)  

    def stop_sweep(self):
        print("Stopped measurement")
        self.stop_measurement = True        

    def start_liv_sweep(self):
        self.stop_measurement = False
        compliance = float(self.compliance_entry.get()) / 1000

        # Initialize SMU
        self.keithley = init_keithley(
            rm,
            self.keithley_address.get(),
            source_mode='volt',
            compliance=compliance
        )

        mode = self.lightMode_var.get()

        thermo_id = None

        if self.osc_address.get() == "None (IV)":
            print('WARN: IV mode selected; no optical data will be measured.')
            mode = None
        elif mode == 'osc':
            # Connect to and initialize oscilloscope
            self.detector = rm.open_resource(self.osc_address.get())
            self.detector.write("*RST")
            self.detector.write("*CLS")
            self.detector.write(":CHANnel%d:IMPedance %s" % (self.light_channel.get(), channelImpedance(self.light_channel_impedance.get())))
            self.detector.write(":TIMebase:RANGe 2E-6")

            vertScaleLight = 0.001
            self.detector.write(":CHANNEL%d:SCALe %.3f" % (self.light_channel.get(), vertScaleLight))
            self.detector.write(":CHANnel%d:DISPlay ON" % self.light_channel.get())
            self.detector.write(":CHANnel%d:OFFset %.3fV" % (self.light_channel.get(), 2 * vertScaleLight))
            totalDisplayCurrent = 6 * vertScaleLight

        elif mode == 'thermo':
            self.thermopile, thermo_id = init_thermopile(
                rm,
                self.osc_address.get(),
                self.wavelength_entry.get()
            )

        elif mode == 'SourceMeter':
            self.detector = init_detector(rm, self.osc_address.get(), mode)
            thermo_id = mode

        # Build voltage array
        if self.radiobutton_var.get() == 'Lin':
            stepSize = round(float(self.step_size_entry.get()) / 1000, 3)
            startV = float(self.start_voltage_entry.get())
            stopV = float(self.stop_voltage_entry.get())
            self.voltage_array = arange(startV, stopV, stepSize)
            self.voltage_array = append(self.voltage_array, stopV)
        elif self.radiobutton_var.get() == 'Log':
            voltage_source_pos = logspace(-4, log10(float(self.stop_voltage_entry.get())), int(self.num_of_pts_entry.get()) / 2)
            voltage_source_neg = -logspace(log10(abs(float(self.start_voltage_entry.get()))), -4, int(self.num_of_pts_entry.get()) / 2)
            self.voltage_array = append(voltage_source_neg, voltage_source_pos)

        self.current = zeros(len(self.voltage_array), float)
        self.light = zeros(len(self.voltage_array), float)
        self.live_plot.reset()


        for i in range(len(self.voltage_array)):
            if self.stop_measurement == False:
                self.set_voltage(round(self.voltage_array[i], 3))
                sleep(0.1)
                self.current[i] = eval(self.keithley.query("read?"))

                light_ampl_osc = read_light(
                    self.detector,
                    self.lightMode_var.get(),
                    thermo_id,
                    self.light_channel.get()
                )
                # Auto-scale vertical if in oscilloscope mode and signal nears top of display
                if mode == 'osc':
                    while light_ampl_osc > 0.9 * totalDisplayCurrent:
                        vertScaleLight = incrOscVertScale(vertScaleLight)
                        totalDisplayCurrent = 6 * vertScaleLight
                        self.detector.write(":CHANNEL%d:SCALe %.3f" % (self.light_channel.get(), float(vertScaleLight)))
                        light_ampl_osc = read_light(
                            self.detector,
                            self.lightMode_var.get(),
                            thermo_id,
                            self.light_channel.get()
                        )

                self.light[i] = light_ampl_osc
                self.live_plot.add_point(self.current[i] * 1000, self.light[i] * 1000, self.voltage_array[i])
            elif self.stop_measurement == True:
                break

        # Turn off output
        self.keithley.write("outp off")

        # Thermopile cleanup
        if mode == 'thermo':
            self.thermopile.write('*COU')
            self.thermopile.close()

        # Save data to file
        txtDir = self.txt_dir_entry.get()
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = 'cwLIV_' + self.device_name_entry.get() + '_' + timestamp
        filepath = os.path.join(txtDir + '/' + filename + '.txt')
        with open(filepath, 'w+') as fd:
            fd.writelines('Device voltage (V)\tDevice current (A)\tPhotodetector current (W)\n')
            for i in range(len(self.voltage_array)):
                fd.write(str(round(self.voltage_array[i], 5)) + '\t')
                fd.write(str(self.current[i]) + '\t')
                fd.write(str(self.light[i]) + '\n')

                # Plot
        fig, ax1 = plt.subplots()
        ax2 = ax1.twinx()
        ax1.set_ylabel('Power per facet (mW)', color='black')
        ax1.set_xlabel('Current (mA)')
        ax2.set_ylabel('Voltage (V)', color='blue')
        ax2.plot(self.current * 1000, self.voltage_array, color='blue', label='I-V Characteristic')
        ax1.plot(self.current * 1000, 1000 * self.light, color='black', label='L-I Characteristic')

        plotString = ('Device Name: ' + self.device_name_entry.get() + '\nTest Type: CW\n' +
                      'Temperature (' + u'\u00B0' + 'C): ' + self.device_temp_entry.get() +
                      '\n' + 'Device Dimensions: ' + self.device_dim_entry.get() +
                      ' (' + u'\u03BC' + 'm x ' + u'\u03BC' + 'm)\n' +
                      'Test Structure or Laser: ' + self.test_laser_button_var.get())

        plt.figtext(0.02, 0.02, plotString, fontsize=12)
        plt.subplots_adjust(bottom=0.3)

        if not os.path.exists(self.plot_dir_entry.get()):
            try:
                os.makedirs(self.plot_dir_entry.get())
            except Exception:
                print('Error: Creating directory: ' + self.plot_dir_entry.get())

        plt.savefig(self.plot_dir_entry.get() + '/' + filename + ".png")

        # Convert current and light readings to mA and mW
        self.current[:] = [x*1000 for x in self.current]
        self.light[:] = [x*1000 for x in self.light]
        export_to_origin(self.current, self.voltage_array, self.light, self.device_name_entry.get())

                

    """
    Function referenced when: setting voltage within the start_iv_sweep function
    Description: Connect to the Keithley, provide what voltage should be set
    read the corresponding current
    """

    def set_voltage(self, voltage):
        keithley = rm.open_resource(self.keithley_address.get())
        keithley.delay = 0.1    # Necessary for GPIB connection?
        keithley.write("sour:func volt")
        keithley.write("sens:curr:rang:auto on")
        keithley.write("sens:func 'curr'")
        keithley.write("form:elem curr")
        keithley.write("outp on")
        keithley.write("sour:volt:lev " + str(voltage))
        curr = keithley.query('READ?')

        return curr

    # Implement multi-threading to allow the use of the main window while running a sweep
    # def stop_pressed(self):
    #     self.keithley.write('outp off')
    #     self.stop_button.config(state=DISABLED)
    #     # Return from function

    """
    Function referenced when: Lin radiobutton is selected
    Description: When in linear mode, we use a step size for plotting,
    so disabled the number of points entry box.
    """

    def lin_selected(self):
        self.num_of_pts_entry.config(state=DISABLED)
        self.step_size_entry.config(state=NORMAL)

    """
    Function referenced when: Log radiobutton is selected
    Description: When in logarithmic mode, we use a number of points for plotting,
    so disabled the step size entry box.
    """

    def log_selected(self):
        self.num_of_pts_entry.config(state=NORMAL)
        self.step_size_entry.config(state=DISABLED)

    """
    Function referenced when: Thermopile radiobutton is selected
    Description: When in thermopile mode, we do not need to set the oscilloscope
    channels, so those dropdown boxes are disabled.
    """

    def thermo_selected(self):
        self.light_channel_dropdown.config(state=DISABLED)
        self.light_channel_impedance_dropdown.config(state=DISABLED)
        self.imp_label.config(state=DISABLED)
        self.osc_label.config(state=DISABLED)

    """
    Function referenced when: Oscilloscope radiobutton is selected
    Description: When in oscilloscope mode enable the dropdown boxes
                 for the selection of the light channel/channel impedance.
    """

    def osc_selected(self):
        self.light_channel_dropdown.config(state=NORMAL)
        self.light_channel_impedance_dropdown.config(state=NORMAL)
        self.imp_label.config(state=NORMAL)
        self.osc_label.config(state=NORMAL)

    """
    Function referenced when: Initializing the application window
    Description: Creates the base geometry and all widgets on the top level
    of the application window
    """

    def __init__(self, parent):
        self.master = parent

        # Change font
        def_font = font.nametofont("TkDefaultFont")
        helv36 = font.Font(family="MS PGothic",size=12)
        self.master.option_add("*Font", helv36)

        # Assign window title and geometry
        self.master.title('CW Measurement: L-I-V')
        self.master.columnconfigure(0, weight=1)
        self.master.columnconfigure(1, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.master.rowconfigure(1, weight=1)
        self.master.rowconfigure(2, weight=1)

        """ Sweep settings frame """
        self.setFrame = LabelFrame(self.master, text='Sweep settings')
        # Display settings frame
        self.setFrame.grid(column=0, row=0, sticky='NSEW', padx=(10, 5), pady=(0,5), rowspan=2)
        for c in range(4): self.setFrame.columnconfigure(c, weight=1)
        for r in range(11): self.setFrame.rowconfigure(r, weight=1)

        # Create plot directory label, button, and entry box
        # Plot File Label
        self.plot_dir_label = Label(self.setFrame, text='Plot file directory:')
        self.plot_dir_label.grid(column=1, row=0, sticky='W', columnspan=2)
        # Plot directory Entry Box
        self.plot_dir_entry = Entry(self.setFrame, width=30)
        self.plot_dir_entry.grid(column=1, row=1, padx=(3, 0), columnspan=2)
        # Browse button
        self.plot_dir_file = Button(
            self.setFrame, text='Browse', command=lambda:browse_plot_file(self))
        self.plot_dir_file.grid(column=3, row=1, ipadx=5)

        # Create text directory label, button, and entry box
        # Text file label
        self.txt_dir_label = Label(self.setFrame, text='Text file directory:')
        self.txt_dir_label.grid(column=1, row=2, sticky='W', columnspan=2)
        # Text directory entry box
        self.txt_dir_entry = Entry(self.setFrame, width=30)
        self.txt_dir_entry.grid(column=1, row=3, padx=(3, 0), columnspan=2)
        # Browse button
        self.txt_dir_file = Button(
            self.setFrame, text='Browse', command=lambda:browse_txt_file(self))
        self.txt_dir_file.grid(column=3, row=3, ipadx=5)

        # Step size label
        self.step_size_label = Label(self.setFrame, text='Step size (mV)')
        self.step_size_label.grid(column=1, row=6)
        # Step size entry box
        self.step_size_entry = Entry(self.setFrame, width=5)
        self.step_size_entry.grid(column=1, row=7)

        # Number of points label
        self.numPts = IntVar()
        self.num_of_pts_label = Label(self.setFrame, text='# of points')
        self.num_of_pts_label.grid(column=2, row=6)
        # Number of points entry box
        self.num_of_pts_entry = Entry(
            self.setFrame, textvariable=self.numPts, width=5)
        self.num_of_pts_entry.grid(column=2, row=7)

        # Compliance label
        self.compliance_label = Label(self.setFrame, text='Compliance (mA)')
        self.compliance_label.grid(column=3, row=6, columnspan=2)
        # Compliance entry box
        self.compliance_entry = Entry(self.setFrame, width=5)
        self.compliance_entry.grid(column=3, row=7, columnspan=2)

        # Start voltage label
        self.start_voltage_label = Label(self.setFrame, text='Start (V)')
        self.start_voltage_label.grid(column=1, row=8)
        # Start voltage entry box
        self.start_voltage_entry = Entry(self.setFrame, width=5)
        self.start_voltage_entry.grid(column=1, row=9)

        # Stop voltage label
        self.stop_voltage_label = Label(self.setFrame, text='Stop (V)')
        self.stop_voltage_label.grid(column=2, row=8)
        # Stop voltage entry box
        self.stop_voltage_entry = Entry(self.setFrame, width=5)
        self.stop_voltage_entry.grid(column=2, row=9)

        # Linear, Log, Lin-Log buttons
        self.radiobutton_var = StringVar()
        self.lin_radiobutton = Radiobutton(
            self.setFrame, text='Lin', variable=self.radiobutton_var, command=self.lin_selected, value='Lin')
        self.lin_radiobutton.grid(column=1, row=10, padx=(10, 0), sticky='W')

        self.log_radiobutton = Radiobutton(
            self.setFrame, text='Log', variable=self.radiobutton_var, command=self.log_selected, value='Log')
        self.log_radiobutton.grid(column=2, row=10, sticky='W')

        # The default setting for radiobutton is set to linear sweep
        self.radiobutton_var.set('Lin')

        # Disable # of points entry because Lin is selected
        self.num_of_pts_entry.config(state=DISABLED)
        
        # Stop Button
        self.stop_button = Button(
        self.setFrame, text='Stop', command=self.stop_sweep)
        self.stop_button.grid(column=3, row=9, rowspan=1, ipadx=10, pady=5)

        # Start Button
        self.start_button = Button(
            self.setFrame, text='Start', command=self.start_liv_sweep)
        self.start_button.grid(column=3, row=8, rowspan=2, ipadx=10, pady=5)

        """ Live Plot frame """
        self.plotFrame = LabelFrame(self.master)
        self.plotFrame.grid(column=0, row=2, sticky='NSEW', padx=5, pady=5)
         # Live plot for real-time visualization (dual axis for voltage and light)
        self.plotFrame.columnconfigure(0, weight=1)
        self.plotFrame.rowconfigure(0, weight=1)
        self.live_plot = LivePlotLIV(self.plotFrame)

        """ Device settings frame """
        self.devFrame1 = LabelFrame(self.master, text='Device settings')
        # Display device settings frame
        self.devFrame1.grid(column=1, row=0, sticky='NSEW', padx=(0, 0), pady=(0,0))
        for c in range(2): self.devFrame1.columnconfigure(c, weight=1)
        for r in range(7): self.devFrame1.rowconfigure(r, weight=1)
        
        # Create label for device name entry box
        self.device_name_label = Label(self.devFrame1, text='Device name:')
        self.device_name_label.grid(column=0, row=0, sticky='W')
        # Device name entry box
        self.device_name_entry = Entry(self.devFrame1, width=15)
        self.device_name_entry.grid(column=0, row=1, sticky='W', padx=(0, 0))

        # Create label for device dimensions entry box
        self.device_dim_label = Label(self.devFrame1, text='Device dimensions ' + '(' + u'\u03BC' + 'm x ' + u'\u03BC' + 'm):')
        self.device_dim_label.grid(column=0, row=2, sticky='W')
        # Device dimensions entry box
        self.device_dim_entry = Entry(self.devFrame1, width=15)
        self.device_dim_entry.grid(column=0, row=3, sticky='W', padx=(0, 0))

        self.test_laser_button_var = StringVar()

        self.laser_radiobuttom = Radiobutton(self.devFrame1, text='Laser', variable=self.test_laser_button_var, value='Laser')
        self.laser_radiobuttom.grid(column=0, row=4, padx=(0, 0), sticky='W')
        self.test_radiobuttom = Radiobutton(self.devFrame1, text='Test structure', variable=self.test_laser_button_var, value='TestStructure')
        self.test_radiobuttom.grid(column=1, row=4, padx=(0, 0), sticky='W')

        self.test_laser_button_var.set('Laser')


        # Create label for device temperature entry box
        self.device_temp_label = Label(self.devFrame1, text='Temperature (' + u'\u00B0' +'C):')
        self.device_temp_label.grid(column=1, row=0)
        # Device name entry box
        self.device_temp_entry = Entry(self.devFrame1, width=5)
        self.device_temp_entry.grid(column=1, row=1, sticky='W', padx=(0, 0))


        """ Instrument settings frame """
        self.instrFrame = LabelFrame(self.master, text='Instrument settings')
        # Display device settings frame
        self.instrFrame.grid(column=1, row=1, sticky='NSEW')
        for c in range(4): self.instrFrame.columnconfigure(c, weight=1)
        for r in range(8): self.instrFrame.rowconfigure(r, weight=1)
        # Device addresses
        connected_addresses = list(rm.list_resources())
        # Pulser and scope variables
        self.keithley_address = StringVar()
        self.osc_address = StringVar()

        # If no devices detected
        if size(connected_addresses) == 0:
            connected_addresses = ['No devices detected.']

        # Set the keithley and scope variables to default values
        self.keithley_address.set('Select...')
        self.osc_address.set('Select...')

        # Thermopile, oscilloscope buttons
        self.lightMode_var = StringVar()
        self.thermo_radiobutton = Radiobutton(
            self.instrFrame, text='Thermopile', variable=self.lightMode_var, command=self.thermo_selected, value='thermo')
        self.thermo_radiobutton.grid(column=0, row=0, padx=(10, 0), sticky='W')

        self.osc_radiobutton = Radiobutton(
            self.instrFrame, text='Oscilloscope', variable=self.lightMode_var, command=self.osc_selected, value='osc')
        self.osc_radiobutton.grid(column=1, row=0, sticky='W')

        self.osc_radiobutton = Radiobutton(
            self.instrFrame, text='SourceMeter', variable=self.lightMode_var, command=self.thermo_selected, value='SourceMeter')
        self.osc_radiobutton.grid(column=2, row=0, sticky='W')

        # The default setting for radiobutton is set to linear sweep
        self.lightMode_var.set('osc')

        # Set thermopile wavelength
        self.wavelength_label = Label(self.instrFrame, text='Thermopile Wavelength (nm)')
        self.wavelength_label.grid(column=3, row=1, sticky='W', padx=(10, 0))

        self.wavelength_entry = Entry(self.instrFrame, width=7)
        self.wavelength_entry.grid(column=3, row=2, sticky='W', padx=(10, 0))

        # Disable # of points entry because oscilloscope is selected
        # self.num_of_pts_entry.config(state=DISABLED)

        self.keithley_label = Label(self.instrFrame, text='SMU address')
        self.keithley_label.grid(column=0, row=1, sticky='W', columnspan=2)

        self.keithley_addr = OptionMenu(self.instrFrame, self.keithley_address, *connected_addresses)
        self.keithley_addr.grid(column=0, row=2, padx=5, sticky='W', columnspan=2)

        self.osc_label = Label(self.instrFrame, text='Optical sensor address')
        self.osc_label.grid(column=0, row=3, sticky='W', columnspan=2)

        self.osc_label = Label(self.instrFrame, text='Light channel')
        self.osc_label.grid(column=0, row=5, sticky='W')


        options = ["None (IV)"] + connected_addresses
        self.osc_addr = OptionMenu(self.instrFrame, self.osc_address, *options)
        self.osc_addr.grid(column=0, row=4, padx=5, sticky='W', columnspan=2)
        # Oscilloscope channel options
        channels = [1, 2, 3, 4]

        self.light_channel = IntVar()
        # Set light channel to 1
        self.light_channel.set(1)

        # Light measurement channel dropdown
        self.light_channel_dropdown = OptionMenu(self.instrFrame, self.light_channel, *channels)
        self.light_channel_dropdown.grid(column=0, row=6, padx=5, pady=(0,5), sticky='W')

        self.imp_label = Label(self.instrFrame, text='Channel impedance')
        self.imp_label.grid(column=1, row=5, sticky='W')

        # Oscilloscope Channel
        impedance = ['50' + u'\u03A9', '1M' + u'\u03A9']

        self.light_channel_impedance = StringVar()
        self.light_channel_impedance.set('50' + u'\u03A9')

        self.light_channel_impedance_dropdown = OptionMenu(self.instrFrame, self.light_channel_impedance, *impedance)
        self.light_channel_impedance_dropdown.grid(column=1, row=6, padx=5,pady=(0,5), sticky='W')

        # Save/Load config buttons
        add_config_buttons(self, self.devFrame1, 'CW_LIV', row=6)

        self.build_tec_frame()
        self.update_tec_readback()
