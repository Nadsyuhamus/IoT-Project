import serial
ser = serial.Serial('COM6', 9600)
print(ser.is_open)
ser.close()