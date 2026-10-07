"""crease_physics.py — THE definitive elastoplastic crease model for the carton flap (Box A spec).

The crease is NOT a USD joint drive: it is a material model applied as an external joint effort
EVERY PHYSICS STEP by your controller/env. The USD files here contain the passive joint only
(limits ±185°, armature 0.006, NO drive); pair them with this module.

Model (isotropic hardening):
    e       = q - rest                      # elastic deflection (rad); q = joint pos, rest = plastic set
    My_cur  = My0 + H * |rest|              # current yield moment (hardening: deeper folds resist more)
    M_el    = clip(k * e, -My_cur, +My_cur) # elastic moment, capped at yield
    rest   += (k * e - M_el) / k            # plastic flow past yield (rest state follows q)
    tau     = clip(-M_el - c * qd, -CLIP, +CLIP)   # applied joint effort (opposes deflection + damping)

DEFINITIVE coefficients (file defaults, Box A):
    k    = 3.5     # elastic stiffness  [N*m/rad]
    My0  = 0.85    # initial yield moment [N*m]
    H    = 0.55    # hardening slope [N*m/rad of plastic set]
    c    = 0.28    # damping [N*m*s/rad]   (HARD CAP: never exceed 0.4 — numerically explodes)
    CLIP = 3.6     # torque clamp [N*m]

Facts you will need:
- OPENING is the NEGATIVE joint direction on these assets (flap hinged at the +y top edge).
- Initialize rest = -ajar when you pre-crease the flap to an initial angle `ajar` (rad, positive-open).
- To PLASTICALLY HOLD at angle R you must press to  R + (My0 + H*R)/k  (radians). With the ±185° joint
  limit this caps the holdable set at ~148 deg.
- Apply per PHYSICS step (not control step). Keep coefficients per-flap if you domain-randomize.
- Verification protocol: 12 s torque ramp to -3 N*m on the hinge should reproduce the reference
  open/rest curves bit-for-bit (see README; regression gate < 1 deg).
"""
import torch


class ElastoplasticCrease:
    K, MY0, HH, CC, CLIP = 3.5, 0.85, 0.55, 0.28, 3.6

    def __init__(self, num_envs, device, k=K, my0=MY0, h=HH, c=CC, clip=CLIP):
        self.k = torch.full((num_envs,), float(k), device=device)
        self.my0 = torch.full((num_envs,), float(my0), device=device)
        self.h = torch.full((num_envs,), float(h), device=device)
        self.c = torch.full((num_envs,), float(c), device=device)
        self.clip = float(clip)
        self.rest = torch.zeros(num_envs, device=device)

    def reset(self, env_ids, ajar_rad):
        """ajar_rad: positive opening amount; joint convention: opening = negative q."""
        self.rest[env_ids] = -ajar_rad

    def step(self, q, qd):
        """q, qd: crease joint position/velocity [rad, rad/s]. Returns joint effort tau [N*m]."""
        e = q - self.rest
        my_cur = self.my0 + self.h * self.rest.abs()
        mr = self.k * e
        mel = torch.clamp(mr, -my_cur, my_cur)
        self.rest = self.rest + (mr - mel) / self.k
        tau = torch.clamp(-mel - self.c * qd, -self.clip, self.clip)
        return torch.nan_to_num(tau, nan=0.0)
