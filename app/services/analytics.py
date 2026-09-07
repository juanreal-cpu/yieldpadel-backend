import logging
from datetime import date, timedelta, time
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.slot import TimeSlot, SlotStatus
from app.models.court import Court

logger = logging.getLogger(__name__)

BLOCKS_90_MIN = [
    (time(6, 0), time(7, 30)),
    (time(7, 30), time(9, 0)),
    (time(9, 0), time(10, 30)),
    (time(10, 30), time(12, 0)),
    (time(12, 0), time(13, 30)),
    (time(13, 30), time(15, 0)),
    (time(15, 0), time(16, 30)),
    (time(16, 30), time(18, 0)),
    (time(18, 0), time(19, 30)),
    (time(19, 30), time(21, 0)),
    (time(21, 0), time(22, 30)),
    (time(22, 30), time(23, 59)),
]

DAY_NAMES_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DAY_SHORTS_ES = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
MONTH_NAMES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


class AnalyticsService:
    @staticmethod
    async def get_weekly_occupancy_matrix(
        db: AsyncSession,
        start_date: Optional[date] = None,
        sport: Optional[str] = "PADEL",
    ) -> Dict[str, Any]:
        """
        Calcula la matriz semanal de ocupación (Horas vs Días), RevPAST,
        y comparativas con Semana Anterior (WoW) y Mes Anterior (MoM, 28 días).
        """
        if not start_date:
            start_date = date.today()

        monday = start_date - timedelta(days=start_date.weekday())
        sunday = monday + timedelta(days=6)

        curr_dates = [monday + timedelta(days=i) for i in range(7)]
        prev_week_dates = [monday - timedelta(days=7) + timedelta(days=i) for i in range(7)]
        prev_month_dates = [monday - timedelta(days=28) + timedelta(days=i) for i in range(7)]

        all_queried_dates = curr_dates + prev_week_dates + prev_month_dates
        sport_upper = (sport or "PADEL").upper()

        court_q = select(Court).where(Court.is_active == True)
        if sport_upper != "ALL":
            court_q = court_q.where(Court.sport_type == sport_upper)
        res_courts = await db.execute(court_q)
        active_courts = res_courts.scalars().all()
        num_courts = len(active_courts)
        if num_courts == 0:
            num_courts = 5 if sport_upper == "PADEL" else (2 if sport_upper == "PICKLEBALL" else 1)

        slot_q = select(TimeSlot).where(TimeSlot.date.in_(all_queried_dates))
        if sport_upper != "ALL":
            slot_q = slot_q.where(TimeSlot.sport_type == sport_upper)
        res_slots = await db.execute(slot_q)
        all_slots = res_slots.scalars().all()

        slots_by_date: Dict[date, List[TimeSlot]] = {}
        for s in all_slots:
            slots_by_date.setdefault(s.date, []).append(s)

        has_prev_week_data = any(d in slots_by_date for d in prev_week_dates)
        has_prev_month_data = any(d in slots_by_date for d in prev_month_dates)

        def is_slot_booked(s: TimeSlot) -> bool:
            status_str = str(getattr(s, "status", "")).upper()
            slot_type_str = str(getattr(s, "slot_type", "")).upper()
            mode_str = str(getattr(s, "mode", "")).upper()

            if status_str in ("FULLY_BOOKED", "SLOTSTATUS.FULLY_BOOKED", "BOOKED", "CLOSED"):
                return True
            if slot_type_str in ("AMERICANO", "TOURNAMENT"):
                return True
            if s.capacity and s.booked_spots >= s.capacity:
                return True
            if s.booked_spots > 0 and mode_str in ("FULL_COURT", "SLOTMODE.FULL_COURT"):
                return True
            if s.players_names and len(s.players_names) > 0:
                return True
            return False

        def get_slot_booked_fraction(s: TimeSlot) -> float:
            if is_slot_booked(s):
                return 1.0
            if s.capacity and s.capacity > 0 and s.booked_spots:
                return min(1.0, float(s.booked_spots) / float(s.capacity))
            return 0.0

        def get_slot_revenue(s: TimeSlot) -> float:
            base_p = float(s.total_price or Decimal("0.00"))
            if is_slot_booked(s):
                return base_p
            if s.capacity and s.capacity > 0 and s.booked_spots:
                return base_p * (float(s.booked_spots) / float(s.capacity))
            return 0.0

        def compute_cell_metrics(day_date: date, b_start: time, b_end: time) -> Dict[str, Any]:
            day_slots = slots_by_date.get(day_date, [])
            matching_slots = []
            for s in day_slots:
                s_start = s.start_time
                s_end = time(23, 59) if (s.end_time.hour == 0 and s.end_time.minute == 0) else s.end_time
                if s_start < b_end and s_end > b_start:
                    matching_slots.append(s)

            if not matching_slots:
                return {
                    "total_slots": num_courts,
                    "slots_booked": 0,
                    "occupancy_percentage": 0.0,
                    "average_revenue": 0.0,
                    "total_revenue": 0.0,
                    "has_slots": False,
                }

            total_s = max(len(matching_slots), num_courts)
            booked_frac_sum = sum(get_slot_booked_fraction(s) for s in matching_slots)
            booked_count = round(booked_frac_sum)
            total_rev = sum(get_slot_revenue(s) for s in matching_slots)
            occ_pct = round((booked_frac_sum / total_s) * 100.0, 1) if total_s > 0 else 0.0
            avg_rev = round(total_rev / total_s, 0) if total_s > 0 else 0.0

            return {
                "total_slots": total_s,
                "slots_booked": booked_count,
                "occupancy_percentage": occ_pct,
                "average_revenue": avg_rev,
                "total_revenue": round(total_rev, 0),
                "has_slots": True,
            }

        def get_heat_level(occ_pct: float) -> str:
            if occ_pct <= 0.0:
                return "zero"
            elif occ_pct <= 40.0:
                return "low"
            elif occ_pct <= 75.0:
                return "medium"
            else:
                return "high"

        matrix_rows = []
        total_curr_slots_sum = 0
        total_curr_booked_sum = 0
        total_curr_revenue_sum = 0.0
        dead_cells_count = 0

        prev_week_occ_sum = 0.0
        prev_week_rev_sum = 0.0
        prev_week_slots_count = 0

        prev_month_occ_sum = 0.0
        prev_month_rev_sum = 0.0
        prev_month_slots_count = 0

        for b_idx, (b_start, b_end) in enumerate(BLOCKS_90_MIN):
            b_label = f"{b_start.strftime('%H:%M')} - {b_end.strftime('%H:%M')}"
            row_days = []

            for d_idx, d_curr in enumerate(curr_dates):
                curr_metric = compute_cell_metrics(d_curr, b_start, b_end)
                occ = curr_metric["occupancy_percentage"]
                total_curr_slots_sum += curr_metric["total_slots"]
                total_curr_booked_sum += curr_metric["slots_booked"]
                total_curr_revenue_sum += curr_metric["total_revenue"]
                if occ < 20.0:
                    dead_cells_count += 1

                delta_wow = None
                delta_wow_rev = None
                if has_prev_week_data:
                    d_prev_w = prev_week_dates[d_idx]
                    pw_metric = compute_cell_metrics(d_prev_w, b_start, b_end)
                    if pw_metric["has_slots"]:
                        delta_wow = round(occ - pw_metric["occupancy_percentage"], 1)
                        delta_wow_rev = round(curr_metric["average_revenue"] - pw_metric["average_revenue"], 0)
                        prev_week_occ_sum += pw_metric["occupancy_percentage"]
                        prev_week_rev_sum += pw_metric["total_revenue"]
                        prev_week_slots_count += pw_metric["total_slots"]

                delta_mom = None
                delta_mom_rev = None
                if has_prev_month_data:
                    d_prev_m = prev_month_dates[d_idx]
                    pm_metric = compute_cell_metrics(d_prev_m, b_start, b_end)
                    if pm_metric["has_slots"]:
                        delta_mom = round(occ - pm_metric["occupancy_percentage"], 1)
                        delta_mom_rev = round(curr_metric["average_revenue"] - pm_metric["average_revenue"], 0)
                        prev_month_occ_sum += pm_metric["occupancy_percentage"]
                        prev_month_rev_sum += pm_metric["total_revenue"]
                        prev_month_slots_count += pm_metric["total_slots"]

                row_days.append({
                    "date": d_curr.strftime("%Y-%m-%d"),
                    "day_name": DAY_NAMES_ES[d_idx],
                    "day_short": DAY_SHORTS_ES[d_idx],
                    "day_num": d_curr.strftime("%d"),
                    "total_slots": curr_metric["total_slots"],
                    "slots_booked": curr_metric["slots_booked"],
                    "occupancy_percentage": occ,
                    "average_revenue": curr_metric["average_revenue"],
                    "total_revenue": curr_metric["total_revenue"],
                    "heat_level": get_heat_level(occ),
                    "delta_last_week": delta_wow,
                    "delta_last_month": delta_mom,
                    "delta_last_week_rev": delta_wow_rev,
                    "delta_last_month_rev": delta_mom_rev,
                })

            matrix_rows.append({
                "time_block": {
                    "index": b_idx,
                    "start_time": b_start.strftime("%H:%M"),
                    "end_time": b_end.strftime("%H:%M"),
                    "label": b_label,
                },
                "days": row_days,
            })

        avg_occ = round((total_curr_booked_sum / total_curr_slots_sum) * 100.0, 1) if total_curr_slots_sum > 0 else 0.0
        weekly_revpast = round(total_curr_revenue_sum / total_curr_slots_sum, 0) if total_curr_slots_sum > 0 else 0.0

        dead_courts_count = 0
        if active_courts:
            for court in active_courts:
                c_slots = [s for s in all_slots if s.date in curr_dates and s.court_id == court.id]
                if not c_slots:
                    dead_courts_count += 1
                else:
                    c_booked = sum(1 for s in c_slots if is_slot_booked(s))
                    c_occ = (c_booked / len(c_slots)) * 100.0
                    if c_occ < 20.0:
                        dead_courts_count += 1
        elif avg_occ < 20.0:
            dead_courts_count = num_courts

        delta_wow_summary_occ = None
        delta_wow_summary_revpast = None
        if has_prev_week_data and prev_week_slots_count > 0:
            prev_w_avg_occ = (prev_week_occ_sum / (len(BLOCKS_90_MIN) * 7))
            prev_w_revpast = prev_week_rev_sum / prev_week_slots_count
            delta_wow_summary_occ = round(avg_occ - prev_w_avg_occ, 1)
            delta_wow_summary_revpast = round(weekly_revpast - prev_w_revpast, 0)

        delta_mom_summary_occ = None
        delta_mom_summary_revpast = None
        if has_prev_month_data and prev_month_slots_count > 0:
            prev_m_avg_occ = (prev_month_occ_sum / (len(BLOCKS_90_MIN) * 7))
            prev_m_revpast = prev_month_rev_sum / prev_month_slots_count
            delta_mom_summary_occ = round(avg_occ - prev_m_avg_occ, 1)
            delta_mom_summary_revpast = round(weekly_revpast - prev_m_revpast, 0)

        week_label = f"{monday.strftime('%d')} - {sunday.strftime('%d')} {MONTH_NAMES_ES[sunday.month - 1]} {sunday.year}"

        days_header = [
            {
                "date": d.strftime("%Y-%m-%d"),
                "day_name": DAY_NAMES_ES[idx],
                "day_short": DAY_SHORTS_ES[idx],
                "day_num": d.strftime("%d"),
                "month_short": MONTH_NAMES_ES[d.month - 1],
            }
            for idx, d in enumerate(curr_dates)
        ]

        time_blocks_header = [
            {
                "index": idx,
                "start_time": b[0].strftime("%H:%M"),
                "end_time": b[1].strftime("%H:%M"),
                "label": f"{b[0].strftime('%H:%M')} - {b[1].strftime('%H:%M')}",
            }
            for idx, b in enumerate(BLOCKS_90_MIN)
        ]

        return {
            "start_date": monday.strftime("%Y-%m-%d"),
            "end_date": sunday.strftime("%Y-%m-%d"),
            "prev_week_date": (monday - timedelta(days=7)).strftime("%Y-%m-%d"),
            "next_week_date": (monday + timedelta(days=7)).strftime("%Y-%m-%d"),
            "week_label": week_label,
            "sport": sport_upper,
            "summary": {
                "average_occupancy": avg_occ,
                "total_revenue": round(total_curr_revenue_sum, 0),
                "weekly_revpast": weekly_revpast,
                "dead_courts_count": dead_courts_count,
                "dead_cells_count": dead_cells_count,
                "total_slots": total_curr_slots_sum,
                "total_booked_slots": total_curr_booked_sum,
                "delta_last_week_occupancy": delta_wow_summary_occ,
                "delta_last_month_occupancy": delta_mom_summary_occ,
                "delta_last_week_revpast": delta_wow_summary_revpast,
                "delta_last_month_revpast": delta_mom_summary_revpast,
            },
            "days": days_header,
            "time_blocks": time_blocks_header,
            "matrix": matrix_rows,
        }
