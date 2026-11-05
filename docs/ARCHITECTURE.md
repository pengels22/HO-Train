# Architecture

Business logic is separated from hardware adapters. Simulation is the default. Locomotive, tracking, routing, actuator, automation, and safety modules communicate through typed state and explicit interfaces. Hardware initialization must be an explicit deployment decision and must fail safe.
