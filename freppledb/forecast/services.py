#
# Copyright (C) 2023 by frePPLe bv
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

from datetime import date, datetime
from dateutil.parser import parse
import json

from channels.db import database_sync_to_async
from channels.generic.http import AsyncHttpConsumer

from freppledb.common.models import Comment
from freppledb.forecast.models import Forecast
from freppledb.input.models import Item, Location, Customer, Buffer


class ForecastService(AsyncHttpConsumer):
    """
    Processes forecast update messages in these formats:
    - From forecast editor:
      {item, location, customer, buckets:[{startdate, endate, bucket, msr1, msr2}]}
    - From forecast report (regular jqgrid save) and excel upload:
      [{item, location, customer, bucket, startdate, endate, msr1, msr2}]
    """

    msgtemplate = """
        <!doctype html>
        <html lang="en">
            <head>
            <meta http-equiv="content-type" content="text/html; charset=utf-8">
            </head>
            <body>%s</body>
        </html>
        """

    @database_sync_to_async
    def updateForecastMethod(self, item, location, customer, method):
        Forecast.objects.all().using(self.scope["database"]).filter(
            item=item, location=location, customer=customer
        ).update(method=method)

    @database_sync_to_async
    def updateComment(self, commenttype, comment, item, location, customer):
        if commenttype == "item" and item:
            Comment(
                content_object=Item.objects.using(self.scope["database"]).get(
                    name=item.name
                ),
                user=self.scope["user"],
                comment=comment,
            ).save(using=self.scope["database"])
        elif commenttype == "location" and location:
            Comment(
                content_object=Location.objects.using(self.scope["database"]).get(
                    name=location.name
                ),
                user=self.scope["user"],
                comment=comment,
            ).save(using=self.scope["database"])
        elif commenttype == "customer" and customer:
            Comment(
                content_object=Customer.objects.using(self.scope["database"]).get(
                    name=customer.name
                ),
                user=self.scope["user"],
                comment=comment,
            ).save(using=self.scope["database"])
        elif commenttype == "itemlocation":
            # TODO buffer object may not exist
            Comment(
                content_object=Buffer.objects.all()
                .using(self.scope["database"])
                .filter(item__name=item.name, location__name=location.name)
                .first(),
                user=self.scope["user"],
                comment=comment,
            ).save(using=self.scope["database"])
        else:
            raise Exception("Invalid comment type")

    async def handle(self, body):
        errors = []
        try:
            import frepple

            if self.scope["method"] != "POST":
                self.scope["response_headers"].append((b"Content-Type", b"text/html"))
                await self.send_response(
                    401,
                    (self.msgtemplate % "Only POST requests allowed").encode(),
                    headers=self.scope["response_headers"],
                )
                return

            # Check permissions
            if not self.scope["user"].has_perm("forecast.change_forecast"):
                self.scope["response_headers"].append((b"Content-Type", b"text/html"))
                await self.send_response(
                    403,
                    (self.msgtemplate % "Permission denied").encode(),
                    headers=self.scope["response_headers"],
                )
                return

            data = json.loads(body.decode("utf-8"))

            if isinstance(data, list):
                # Message format #1
                for bckt in data:
                    # Validate
                    try:
                        item = frepple.item(name=bckt["item"], action="C")
                    except:
                        item = None
                        errors.append("Item not found: %s" % bckt["item"])
                    try:
                        location = frepple.location(name=bckt["location"], action="C")
                    except:
                        location = None
                        errors.append("Location not found: %s" % bckt["location"])
                    try:
                        customer = frepple.customer(name=bckt["customer"], action="C")
                    except:
                        customer = None
                        errors.append("Customer not found: %s" % bckt["customer"])
                    if customer and item and location:
                        try:
                            args = {
                                "item": item,
                                "location": location,
                                "customer": customer,
                            }
                            bucket = bckt.get("bucket", None)
                            if bucket:
                                args["bucket"] = bucket.lower()
                            startdate = bckt.get("startdate", None)
                            if startdate:
                                # Guess! the date format, using Month-Day-Year as preference
                                # to resolve ambiguity.
                                # This default style is also the default datestyle in Postgres
                                # https://www.postgresql.org/docs/9.1/runtime-config-client.html#GUC-DATESTYLE
                                args["startdate"] = parse(
                                    startdate, yearfirst=False, dayfirst=False
                                )
                            enddate = bckt.get("enddate", None)
                            if enddate:
                                # Guess! the date format, using Month-Day-Year as preference
                                # to resolve ambiguity.
                                # This default style is also the default datestyle in Postgres
                                # https://www.postgresql.org/docs/9.1/runtime-config-client.html#GUC-DATESTYLE
                                args["enddate"] = parse(
                                    enddate, yearfirst=False, dayfirst=False
                                )
                            for key, val in bckt.items():
                                if key not in (
                                    "id",
                                    "item",
                                    "location",
                                    "customer",
                                    "bucket",
                                    "startdate",
                                    "enddate",
                                    "forecast",
                                ):
                                    args[key] = float(val)
                            frepple.setForecast(**args)
                        except Exception as e:
                            errors.append("Error processing %s" % e)
            else:
                # Message format #2

                # Validate
                try:
                    item = frepple.item(name=data["item"], action="C")
                except:
                    item = None
                    errors.append("Item not found: %s" % data["item"])
                try:
                    location = frepple.location(name=data["location"], action="C")
                except:
                    location = None
                    errors.append("Location not found: %s" % data["location"])
                try:
                    customer = frepple.customer(name=data["customer"], action="C")
                except:
                    customer = None
                    errors.append("Customer not found: %s" % data["customer"])

                # Update forecast method
                mthd = data.get("forecastmethod", None)
                if (
                    mthd
                    and self.scope["user"].has_perm("forecast.change_forecast")
                    and item
                    and customer
                    and location
                ):
                    try:
                        await self.updateForecastMethod(
                            item.name,
                            location.name,
                            customer.name,
                            mthd,
                        )
                    except Exception:
                        errors.append("Exception updating forecast method")

                # Update forecast values
                if (
                    "buckets" in data
                    and item
                    and location
                    and customer
                    and self.scope["user"].has_perm("forecast.change_forecast")
                ):
                    for bckt in data["buckets"]:
                        try:
                            args = {
                                "item": item,
                                "location": location,
                                "customer": customer,
                            }
                            bucket = bckt.get("bucket", None)
                            if bucket:
                                args["bucket"] = bucket.lower()
                            startdate = bckt.get("startdate", None)
                            if startdate:
                                # Guess! the date format, using Month-Day-Year as preference
                                # to resolve ambiguity.
                                # This default style is also the default datestyle in Postgres
                                # https://www.postgresql.org/docs/9.1/runtime-config-client.html#GUC-DATESTYLE
                                args["startdate"] = parse(
                                    startdate, yearfirst=False, dayfirst=False
                                )
                            enddate = bckt.get("enddate", None)
                            if enddate:
                                # Guess! the date format, using Month-Day-Year as preference
                                # to resolve ambiguity.
                                # This default style is also the default datestyle in Postgres
                                # https://www.postgresql.org/docs/9.1/runtime-config-client.html#GUC-DATESTYLE
                                args["enddate"] = parse(
                                    enddate, yearfirst=False, dayfirst=False
                                )
                            for key, val in bckt.items():
                                if key not in ("id", "bucket", "startdate", "enddate"):
                                    args[key] = float(val)
                            frepple.setForecast(**args)
                        except Exception as e:
                            errors.append("Error processing %s" % e)

                # Save a new comment
                if (
                    "commenttype" in data
                    and "comment" in data
                    and self.scope["user"].has_perm("common.add_comment")
                ):
                    try:
                        await self.updateComment(
                            data["commenttype"],
                            data["comment"],
                            item,
                            location,
                            customer,
                        )
                    except Exception:
                        errors.append(b"Exception entering comment")

            # Reply
            self.scope["response_headers"].append(
                (b"Content-Type", b"application/json")
            )
            if errors:
                answer = {"errors": errors}
            else:
                answer = {"OK": 1}
            await self.send_response(
                500 if errors else 200,
                json.dumps(answer).encode(),
                headers=self.scope["response_headers"],
            )
        except Exception as e:
            errors.append(str(e).encode())
            await self.send_response(
                500,
                json.dumps({"errors": errors}).encode(),
                headers=self.scope["response_headers"],
            )


class FlushService(AsyncHttpConsumer):
    async def handle(self, body):
        import frepple

        self.scope["response_headers"].append((b"Content-Type", b"text/html"))
        try:
            if self.scope["method"] != "POST":
                await self.send_response(
                    401,
                    b"Only POST requests allowed",
                    headers=self.scope["response_headers"],
                )
                return
            if self.scope["path"] == "/flush/manual/":
                frepple.cache.write_immediately = False
            elif self.scope["path"] == "/flush/auto/":
                frepple.cache.flush()
                frepple.cache.write_immediately = True
            else:
                await self.send_response(
                    404,
                    b"Only supported modes are 'manual' and 'auto'",
                    headers=self.scope["response_headers"],
                )
            await self.send_response(200, b"OK", headers=self.scope["response_headers"])
        except Exception as e:
            await self.send_response(
                500, b"Error flushing forecast", headers=self.scope["response_headers"]
            )
