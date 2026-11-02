"""Stop a finite funding approach at its last verified escape, never in battle."""

class FundingApproachLimit(RuntimeError):
    def __init__(self, handler, receipt):
        super().__init__("funding approach reached eight verified wild escapes")
        self.handler, self.receipt = handler, receipt


class BoundedFundingApproach:
    def __init__(self, delegate, reader, emulator, destination):
        self.delegate, self.reader, self.emulator = delegate, reader, emulator
        self.destination = destination
        self.stop_receipt = None

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def handle(self, interruption):
        receipt = self.delegate.handle(interruption)
        if (receipt.kind != "wild_battle" or len(self.delegate.evidence) != 8
                or self.delegate.maximum_flees != 8):
            return receipt
        raw = self.reader.read()
        at = (raw.map_id, raw.player_y, raw.player_x)
        if at == self.destination:
            return receipt
        from .route_executor import RouteExecutionError
        if (not self.delegate.evidence[-1].verified or raw.battle_state != 0
                or at != (receipt.resumed_map, *receipt.resumed_at)
                or not self.reader.read_input_readiness().ready
                or self.reader.read_bottom_dialogue_box_visible()
                or self.reader.read_pending_trainer_battle_identity() is not None
                or self.reader.trainer_engagement_active()
                or self.emulator.pressed_buttons):
            raise RouteExecutionError("funding flee bound lacks a settled verified boundary")
        self.stop_receipt = receipt
        raise FundingApproachLimit(self, receipt)
