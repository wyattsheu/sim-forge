# 2026-10-23 Dragon connected FEM hardware halt

## Finding

Classification: `native_business_halt`.

The monitor and repair timers were enabled and healthy. The latest monitor tick
reported the `dragon` run as `business_halt`; no dragon pipeline descendants
remained. This run passed `image_cleanup` and reached the Genesis diagnostic
loop, so the earlier image-result persistence runtime fault is not the current
failure.

The durable diagnostic recommendation identifies visible gold keychain
hardware as missing from the active single-volume FEM representation. The
segmentation and meshing candidate include the hardware as part label 4. The
candidate contains 1,184 label-4 tetrahedra in a disconnected component whose
nearest distance to the main body component is 1.767 mm. Native component
resolution retained the maximum-volume body component and dropped label 4; the
serialized topology and diagnostic grounding both record zero final hardware
tetrahedra/primitives. The candidate also contains a separate 7-tet sliver.

The official pinned volumetric mesher raises on a multi-component tet domain,
then its guarded resolver retains one maximum-volume component and records
dropped part indices ([upstream source at the installed commit](https://github.com/diaggen/diaggen/blob/3d2d3779613b9253109f63e1ff345b11c9097b70/hag4r/tools/volumetric_meshing.py#L1652-L1668), [component resolver](https://github.com/diaggen/diaggen/blob/3d2d3779613b9253109f63e1ff345b11c9097b70/hag4r/tools/volumetric_meshing.py#L1712-L1815)). The durable native diagnostic states that the current supported path has no multi-body/contact representation for these interlocked rings. It correctly halted rather than treating the single-volume mesh as complete.

The earlier `genesis_dragon_20261023_coarse_connector6` experiment also dropped
source-visible hardware, at a recorded 0.630 mm separation. This run groups the
hardware as one segmentation label, but the disconnected geometry remains.
The failure is therefore not explained by the scheduler or by the previous
image writer fault.

## Change and disposition

No native, runtime, dependency, or environment change was made. The available
native path cannot retain this separated hardware without either dropping it
or inventing a bridge. Both would misrepresent the photographed object. The
failed state and all native artifacts remain intact, and the dragon job was not
requeued. The existing failed queue outcome is preserved for this run.

## Checks

- Monitor and repair timers were active; the monitor status was fresh and
  reported `business_halt` for this run.
- Queue status at investigation time: 7 succeeded, 1 failed (`dragon`), 1
  queued, 0 running. The read-only process observer found no dragon pipeline
  descendants.
- A read-only consistency check passed across the terminal record, component
  resolution report, serialized volume topology, and final diagnostic grounding:
  hardware was present in the candidate and absent from the resolved mesh.
- Installed DiagGen source commit: `3d2d3779613b9253109f63e1ff345b11c9097b70`.
- No tests, GPU work, or readiness recertification were run because no source,
  service, or environment was changed. The repair worker's finish hook retains
  its existing readiness check before releasing its owned HOLD.

Job requeued: no. Completing the dragon asset with the visible hardware intact
requires native support for separate bodies/contact or a geometrically
grounded connected model; neither is currently available through this run's
guarded native controls.
