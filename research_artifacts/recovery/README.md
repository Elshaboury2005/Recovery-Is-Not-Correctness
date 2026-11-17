# Recovery

Recovery endpoints are typed and distinct: infrastructure availability,
application progress, source drain, graceful STOP, terminal status, output
publication, and exact correctness. `T_confirm` is the qualifying-window-end
timestamp minus worker-restore timestamp; the qualifying window duration is
not `T_confirm`.
