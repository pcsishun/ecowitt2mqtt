"""Define aiohttp routes."""
import asyncio
import json
# import pymongo

from typing import Any, Dict, Union

from aiohttp import web
from asyncio_mqtt import Client, MqttError

from const import LOGGER # ecowitt2mqtt
from data import DataProcessor # ecowitt2mqtt
from hass import HassDiscovery # ecowitt2mqtt

from flask import Flask, request
app = Flask(__name__)
 

DEFAULT_MAX_MQTT_CALLS = 10


def _generate_payload(data: Union[Dict[str, Any], float, str]) -> bytes:
    """Generate a binary MQTT payload from input data."""
    if isinstance(data, dict):
        return json.dumps(data).encode("utf-8")

    if isinstance(data, str):
        return data.encode("utf-8")

    return str(data).encode("utf-8")


async def _async_publish_to_hass_discovery(
    client: Client, data: Dict[str, Any], discovery_manager: HassDiscovery
) -> None:
    """Publish data to appropriate topics for Home Assistant Discovery."""
    LOGGER.debug("Publishing according to Home Assistant MQTT Discovery standard")

    try:
        async with client:
            tasks = []
            for key, value in data.items():
                config_payload = discovery_manager.get_config_payload(key, value)
                config_topic = discovery_manager.get_config_topic(key, value)

                tasks.append(
                    client.publish(config_topic, _generate_payload(config_payload))
                )
                tasks.append(
                    client.publish(
                        config_payload["availability_topic"],
                        _generate_payload("online"),
                    )
                )
                tasks.append(
                    client.publish(
                        config_payload["state_topic"],
                        _generate_payload(value),
                        retain=True,
                    )
                )

            await asyncio.gather(*tasks)
    except MqttError as err:
        LOGGER.error("Error while publishing to HASS Discovery: %s", err)
        return

    LOGGER.info("Published to HASS discovery: %s", data)

@app.route('/weathersending', methods=['POST'])
async def _async_publish_to_topic(
    client: Client, data: Dict[str, Any], topic: str
) -> None:
    """Publish data to a single MQTT topic."""
    LOGGER.debug("Publishing entire device payload to single topic: %s", topic)
 
    ## connect to mongodb ## 
    # myclient = pymongo.MongoClient("mongodb://localhost:27017/")
    # mydb = myclient["database_name"]
    # mycol = mydb["collection_name"]

    data_weather = {
        "tempin": float(data['tempin']), 
        "humidityin": float(data['humidityin']), 
        "baromrel":float(data['baromrel']), 
        "baromabs":float(data['baromabs'])
        }
    
    print(data_weather)
    return data_weather

    # mycol.insert_one(data_weather)



    # try:
    #     async with client:
    #         LOGGER.error("Chop Hee OK: " + data)
    #         await client.publish(topic, _generate_payload(data))
    # except MqttError as err:
    #     # print("this err ==> "+err + "and data ==>" + data)
    #     # LOGGER.info("Chop Hee FAIL: %s", data)
    #     LOGGER.error("Error while publishing to %s: %s", topic, err)
    #     return

    # LOGGER.info("Published to %s: %s", topic, data)


async def async_publish_payload(request: web.Request) -> None:
    """Define the endpoint for the Ecowitt device to post data to."""
    args = request.app["args"]

    payload = dict(await request.post())
    LOGGER.debug("Received data from Ecowitt device: %s", payload)

    data_processor = DataProcessor(payload, args)
    data = data_processor.generate_data()

    client = Client(
        args.mqtt_broker,
        port=args.mqtt_port,
        username=args.mqtt_username,
        password=args.mqtt_password,
        logger=LOGGER,
        max_concurrent_outgoing_calls=DEFAULT_MAX_MQTT_CALLS,
    )

    if args.hass_discovery:
        discovery_managers = request.app["hass_discovery_managers"]

        if data_processor.device.unique_id in discovery_managers:
            discovery_manager = discovery_managers[data_processor.device.unique_id]
        else:
            discovery_manager = HassDiscovery(data_processor.device, args)
            discovery_managers[data_processor.device.unique_id] = discovery_manager

        await _async_publish_to_hass_discovery(client, data, discovery_manager)
    else:
        if args.mqtt_topic:
            topic = args.mqtt_topic
        else:
            topic = f"ecowitt2mqtt/{data_processor.device.unique_id}"

        await _async_publish_to_topic(client, data, topic)
