# Helper functions for instruments

def init_keithley(rm, address, source_mode, compliance):
    """
    Initialize a Keithley SMU for CW measurements.

    source_mode: 'curr' or 'volt'
    compliance:  compliance value in A or V (already converted)
    """
    k = rm.open_resource(address)

    k.write("*RST; status:preset; *CLS")
    k.write(f"sour:func {source_mode}")

    if source_mode == 'curr':
        k.write("sens:func 'volt'")
        k.write(f"sens:volt:prot:lev {compliance}")
        k.write("sens:volt:range:auto on")
    else:
        k.write("sens:func 'curr'")
        k.write(f"sens:curr:prot:lev {compliance}")
        k.write("sens:curr:range:auto on")

    k.write("form:elem curr")
    k.write("outp on")

    return k

def init_thermopile(rm, address, wavelength):
    """
    Opens a connection to a thermopile and configures it for the given wavelength.
    Returns: (thermopile_resource, id_string)
    """
    thermopile = rm.open_resource(address)
    id = thermopile.query("*IDN?")
    wavelength = int(wavelength)

    if "integra" in id.lower():
        thermopile.write("*CSU")
        thermopile.timeout = 5000
        thermopile.write_termination = ''
        thermopile.write(f"*PWC{wavelength:05d}")
        print("Thermopile wavelength set to %d nm" % wavelength)

    elif "coherent" in id.lower():
        thermopile.write("*RST")
        thermopile.write(f"CONFigure:WAVElength {wavelength:05d}")
        print("Thermopile wavelength set to %d nm" % wavelength)
        thermopile.write("CONFigure:ZERO")

    else:
        print(f"WARNING: Thermopile '{id}' is not compatible with this system.")

    return thermopile, id

def init_detector(rm, address, detectorID):
    if detectorID == 'SourceMeter':
        k = rm.open_resource(address)
        k.write("*rst; status:preset; *cls")                       # Reset GPIB defaults
        k.write("sour:func:mode curr")                             # Select source function mode as current source
        k.write("sour:curr 0")                                     # Set source level to 10V
        k.write("sens:func 'volt'")
        k.write("sens:volt:prot:lev " + str(21))                   # Set volt compliance
        k.write("sens:volt:range 1")                               # Set volt measure range 100mA
        k.write("outp on")
    return k

def read_light(detector, mode, detectorID, light_channel):
    if detector is None:
        return 0.0
    if detectorID == 'SourceMeter':
            raw = detector.query('READ?')
            return float(raw.split(',')[0])
    if mode == 'thermo':
        if detectorID is None:
            print("WARN: Thermopile not initialized.")
            return 0.0
        if "integra" in detector.lower():
            try:
                raw = detector.query('*CVU')
                return float(raw)
            except ValueError:
                print(f"Thermopile read error: {raw}")
                return 0.0
        elif "coherent" in detectorID.lower():
            try:
                raw = detector.query('READ?')
                return float(raw.split(',')[0])
            except ValueError:
                print(f"Thermopile read error: {raw}")
                return 0.0
        else:
            print(f"WARN: Thermopile {thermo_id} is not compatible with this system.")
            return 0.0
    else:
        return detector.query_ascii_values(
            "SINGLE;*OPC;:MEASure:VAMPlitude? CHANNEL%d" % light_channel
        )[0]
