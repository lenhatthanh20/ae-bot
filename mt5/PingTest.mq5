// PingTest.mq5 - Phase 0 gate: WebRequest to the Mac host and Calendar under Wine.
#property script_show_inputs
input string InpUrl = "http://127.0.0.1:8000/health";

void OnStart()
{
   char data[], res[];
   string hdr;
   ResetLastError();
   int code = WebRequest("GET", InpUrl, "", 5000, data, res, hdr);
   PrintFormat("WebRequest code=%d err=%d body=%.60s", code, GetLastError(), CharArrayToString(res));

   MqlCalendarValue v[];
   datetime now = TimeTradeServer();
   ResetLastError();
   bool ok = CalendarValueHistory(v, now - 7 * 86400, now, NULL, "USD");
   PrintFormat("Calendar ok=%s values=%d err=%d", ok ? "true" : "false", ArraySize(v), GetLastError());
   PrintFormat("TimeGMT=%s TimeTradeServer=%s", TimeToString(TimeGMT()), TimeToString(now));
}
