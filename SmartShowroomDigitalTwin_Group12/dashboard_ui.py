# dashboard_ui.py

PRODUCT_1 = "Apple Vision Pro"
PRODUCT_2 = "Apple Smart Ring"


def get_status_class(status):
    if status == "Browsing":
        return "status-browsing"
    if status == "Interested":
        return "status-interested"
    if status == "Highly Interested":
        return "status-high"
    if status == "Engagement Alert":
        return "status-alert"
    return "status-no"


def render_dashboard(d):
    status1_class = get_status_class(d["status1"])
    status2_class = get_status_class(d["status2"])

    led1_class = "ok" if d["led1"] else "off"
    led2_class = "ok" if d["led2"] else "off"
    buzzer1_class = "alert" if d["buzzer1"] else "off"
    buzzer2_class = "alert" if d["buzzer2"] else "off"

    led1_text = "ON" if d["led1"] else "OFF"
    led2_text = "ON" if d["led2"] else "OFF"
    buzzer1_text = "ON" if d["buzzer1"] else "OFF"
    buzzer2_text = "ON" if d["buzzer2"] else "OFF"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Smart Showroom Dashboard</title>
        <meta http-equiv="refresh" content="2">
        <style>
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f4f6fb;
                color: #1f2937;
            }}
            .header {{
                background: linear-gradient(90deg, #4c1d95, #7c3aed);
                color: white;
                padding: 28px 42px;
            }}
            .header h1 {{ margin: 0; font-size: 32px; }}
            .header p {{ margin-top: 8px; font-size: 15px; }}
            .container {{ padding: 30px 40px; }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
            }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 22px;
                box-shadow: 0 4px 14px rgba(0,0,0,0.08);
                margin-bottom: 20px;
            }}
            .card h2 {{ margin-top: 0; color: #4c1d95; }}
            .value {{ font-size: 32px; font-weight: bold; margin: 10px 0; }}
            .score {{ font-size: 42px; font-weight: bold; color: #7c3aed; }}
            .ok {{ color: #15803d; font-weight: bold; }}
            .alert {{ color: #dc2626; font-weight: bold; }}
            .off {{ color: #6b7280; font-weight: bold; }}
            .pill {{
                display: inline-block;
                padding: 8px 14px;
                border-radius: 20px;
                background: #ede9fe;
                color: #4c1d95;
                font-weight: bold;
                margin-top: 8px;
            }}
            .status-badge {{
                display: inline-block;
                padding: 10px 18px;
                border-radius: 999px;
                font-size: 18px;
                font-weight: 800;
                min-width: 170px;
                text-align: center;
            }}
            .status-no {{ background: #f3f4f6; color: #6b7280; border: 1px solid #d1d5db; }}
            .status-browsing {{ background: #dbeafe; color: #1d4ed8; border: 1px solid #93c5fd; }}
            .status-interested {{ background: #dcfce7; color: #15803d; border: 1px solid #86efac; }}
            .status-high {{ background: #fef3c7; color: #b45309; border: 1px solid #fcd34d; }}
            .status-alert {{
                background: #fee2e2;
                color: #dc2626;
                border: 1px solid #fca5a5;
                animation: pulse 1s infinite;
            }}
            @keyframes pulse {{
                0% {{ transform: scale(1); }}
                50% {{ transform: scale(1.04); }}
                100% {{ transform: scale(1); }}
            }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            td {{ padding: 10px; border-bottom: 1px solid #e5e7eb; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Apple Futuristic Product Showroom</h1>
            <p>Live Raspberry Pi CPS Dashboard | Dwell-Time Analytics | Smart Product Recommendations</p>
        </div>

        <div class="container">
            <div class="card">
                <h2>System Status</h2>
                <div class="value">{d["system_status"]}</div>
                <p><b>Last Updated:</b> {d["timestamp"]}</p>
                <span class="pill">Buzzer + 100% Score at 15 sec | Recommendation at 17 sec</span>
            </div>

            <div class="card">
                <h2>AI Recommendation Engine</h2>
                <div class="value">{d["recommended_product"]}</div>
                <p><b>Recommended items:</b></p>
                <ul>{d["recommendation_reason"]}</ul>
            </div>

            <div class="grid">
                <div class="card">
                    <h2>{PRODUCT_1}</h2>
                    <p class="value">{d["dist1"]} cm</p>
                    <p>Engagement Score</p>
                    <div class="score">{d["score1"]}/100</div>
                    <table>
                        <tr><td>Detection Status</td><td><span class="status-badge {status1_class}">{d["status1"]}</span></td></tr>
                        <tr><td>Dwell Time</td><td>{d["dwell1"]} sec</td></tr>
                        <tr><td>LED Status</td><td class="{led1_class}">{led1_text}</td></tr>
                        <tr><td>Buzzer Status</td><td class="{buzzer1_class}">{buzzer1_text}</td></tr>
                    </table>
                </div>

                <div class="card">
                    <h2>{PRODUCT_2}</h2>
                    <p class="value">{d["dist2"]} cm</p>
                    <p>Engagement Score</p>
                    <div class="score">{d["score2"]}/100</div>
                    <table>
                        <tr><td>Detection Status</td><td><span class="status-badge {status2_class}">{d["status2"]}</span></td></tr>
                        <tr><td>Dwell Time</td><td>{d["dwell2"]} sec</td></tr>
                        <tr><td>LED Status</td><td class="{led2_class}">{led2_text}</td></tr>
                        <tr><td>Buzzer Status</td><td class="{buzzer2_class}">{buzzer2_text}</td></tr>
                    </table>
                </div>
            </div>

            <div class="card">
                <h2>CPS Requirement Coverage</h2>
                <table>
                    <tr><td>Sensor</td><td>2 HC-SR04 ultrasonic sensors detect customer proximity</td></tr>
                    <tr><td>Actuator</td><td>2 LEDs and 2 buzzers respond to detection and high engagement</td></tr>
                    <tr><td>Wireless Communication</td><td>Dashboard is accessed through Raspberry Pi IP address</td></tr>
                    <tr><td>Data Storage</td><td>SQLite stores timestamp, distance, dwell time, score, recommendation, LED and buzzer status</td></tr>
                    <tr><td>Recommendation</td><td>Dashboard recommends add-on products based on engagement score</td></tr>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
