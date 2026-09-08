import asyncio
from app.models import Location
from app.weather import WeatherService
async def main():
    b=await WeatherService().bundle(Location(name='New Delhi',latitude=28.6139,longitude=77.209))
    print('Sources:',b['sources'])
    print('Hourly records:',len(b['hourly']))
    print('Warnings:',b['alerts_status'])
    assert b['hourly'] and b['source_count']>0
    print('LIVE INTEGRATION PASSED')
asyncio.run(main())
