# Pylabrad Configuration

There are a number of environment variables that can be used to configure
labrad, which pylabrad also checks. These are as follows:

- `LABRADHOST`: The hostname of the machine where the labrad manager is running
  (default = localhost).
- `LABRADPORT`: The tcp port on which the labrad manager is listening
  (default = 7682).
- `LABRADPASSWORD`: The password to use when connecting to labrad.
- `LABRAD_TLS`: The transport-layer security (TLS) mode to use. Must be one of
  the following:
  - `starttls`: The default; the initial connection is unencrypted and is then
    upgraded using the STARTTLS mechanism to secure the connection.
  - `on`: The initial connection is encrypted. In this mode the default port
    will be `LABRAD_TLS_PORT` instead of `LABRADPORT`.
  - `off`: No TLS. This means data will be sent in plain text over the network,
    so you must take other precautions to secure it, such as operating over a
    VPN or tunneling labrad through SSH. This can be used for compatibility
    with legacy managers that do not support TLS.
- `LABRAD_TLS_PORT`: The tcp port on which the labrad manager is listening for
  connection that are TLS from the beginning. This is used as the default port
  when `LABRAD_TLS=on` or when you explicitly call `labrad.connect` with the
  option `tls="on"`.

