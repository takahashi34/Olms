import tkinter as tk
from tkinter import Label, Button, Radiobutton, Toplevel, StringVar
import tkinter.messagebox as messagebox

# Import measurement files
from cw import CW_LIV
from vp import VPulse_LIV
from ip import IPulse_LIV

class MeasSelect():

    def __init__(self, parent):
        self.master = parent

        # Assign window title
        self.master.title('Laser Diode Measurement Selection')

        # Create selection buttons
        self.selectedMeasurement = StringVar()

        # Continuous wave (CW) measurement section

        # CW L-I-V measurement button
        self.CW_LIV_radiobutton = Radiobutton(
            self.master, text='Continuous Wave', variable=self.selectedMeasurement, value='CW_LIV', font=('Segoe UI', 10))
        self.CW_LIV_radiobutton.grid(column=0, row=1, padx=(5, 0), sticky='W')

        # Voltage pulsed (VPulse) measurement section

        # VPulse L-I-V measurement button
        self.VPulse_LIV_radiobutton = Radiobutton(
            self.master, text='Voltage Pulsed', variable=self.selectedMeasurement, value='VPulse_LIV', font=('Segoe UI', 10))
        self.VPulse_LIV_radiobutton.grid(
            column=0, row=4, padx=(5, 0), sticky='W')

        # Current pulsed (IPulse) measurement section

        # IPulse L-I-V measurement button
        self.IPulse_LIV_radiobutton = Radiobutton(
            self.master, text='Current Pulsed', variable=self.selectedMeasurement, value='IPulse_LIV', font=('Segoe UI', 10))
        self.IPulse_LIV_radiobutton.grid(
            column=0, row=6, padx=(5, 0), sticky='W')

        # Set default value to CW L-I-V
        self.selectedMeasurement.set('CW_LIV')

        # Open measurement button
        self.measure_button = Button(self.master, text='Open Measurement', command=self.open_measurement_window, font=('Segoe UI', 10))
        self.measure_button.grid(column=2, row=7, padx=(10, 20), pady=(5, 10), sticky='W')

    def open_measurement_window(self):
        top = Toplevel(root)

        if 'CW_LIV' == self.selectedMeasurement.get():
            CWLIV_gui = CW_LIV(top)
        elif 'VPulse_LIV' == self.selectedMeasurement.get():
            VPulseLIV_gui = VPulse_LIV(top)
        elif 'IPulse_LIV' == self.selectedMeasurement.get():
            IPulseLIV_gui = IPulse_LIV(top)
        root.withdraw()

        # When the user closes the measurement window, bring the root window back
        def minimize_root():
            top.destroy()
            root.deiconify()

        top.protocol('WM_DELETE_WINDOW', minimize_root)

# When the user attempts to close the window, double check if they would like to Quit.
def on_closing():
    if messagebox.askokcancel('Quit', 'Do you want to quit?'):
        root.destroy()

root = tk.Tk()


Selection_GUI = MeasSelect(root)
root.protocol('WM_DELETE_WINDOW', on_closing)
root.mainloop()
