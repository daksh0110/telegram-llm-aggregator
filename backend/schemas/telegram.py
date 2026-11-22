from pydantic import BaseModel, ConfigDict


class AddGroup(BaseModel):
    channel_id: int


class TelegramChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    channel_name: str