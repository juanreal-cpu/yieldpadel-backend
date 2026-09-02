import React, { useState, useEffect, useCallback } from 'react';

// Interfaces alineadas con FastAPI Pydantic Schemas
interface TimeSlot {
  id: number;
  court_id: number;
  court_name: string | null;
  date: string;
  start_time: string;
  end_time: string;
  total_price: string;
  price_per_spot: string;
  mode: 'FULL_COURT' | 'SPLIT_MATCH';
  capacity: number;
  booked_spots: number;
  held_spots: number;
  available_spots: number;
  status: 'AVAILABLE' | 'PARTIALLY_BOOKED' | 'FULLY_BOOKED' | 'BLOCKED';
}

interface HoldResponse {
  id: number;
  slot_id: number;
  customer_phone: string;
  customer_name: string;
  spots_held: number;
  amount_to_pay: string;
  expires_at: string;
  status: string;
  payment_reference: string;
}

interface ActivityItem {
  id: string;
  title: string;
  subtitle: string;
  time: string;
  type: 'confirmed' | 'hold' | 'info';
}

const API_BASE = 'http://127.0.0.1:8000';

export default function App() {
  const [slots, setSlots] = useState<TimeSlot[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiOnline, setApiOnline] = useState(false);
  const [modeFilter, setModeFilter] = useState<'ALL' | 'FULL_COURT' | 'SPLIT_MATCH'>('ALL');
  const [selectedSlot, setSelectedSlot] = useState<TimeSlot | null>(null);
  const [activeHolds, setActiveHolds] = useState<HoldResponse[]>([]);
  const [activities, setActivities] = useState<ActivityItem[]>([
    { id: '1', title: 'Sistema Iniciado', subtitle: 'Conexión con FastAPI Core', time: 'Ahora', type: 'info' }
  ]);

  // Formulario de Hold
  const [customerName, setCustomerName] = useState('');
  const [customerPhone, setCustomerPhone] = useState('+57 ');
  const [spotsToHold, setSpotsToHold] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Cargar Slots desde la API
  const fetchSlots = useCallback(async () => {
    try {
      // 1. Ejecutar check de expiraciones previo para asegurar datos frescos
      await fetch(`${API_BASE}/api/v1/holds/check-expirations`, { method: 'POST' }).catch(() => {});

      // 2. Obtener lista de slots
      const url = new URL(`${API_BASE}/api/v1/slots/`);
      url.searchParams.append('only_available', 'false');
      if (modeFilter !== 'ALL') {
        url.searchParams.append('mode', modeFilter);
      }

      const res = await fetch(url.toString());
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data: TimeSlot[] = await res.json();
      setSlots(data);
      setApiOnline(true);
    } catch (err) {
      console.error('Error fetching slots:', err);
      setApiOnline(false);
    } finally {
      setLoading(false);
    }
  }, [modeFilter]);

  useEffect(() => {
    fetchSlots();
    const interval = setInterval(fetchSlots, 8000); // Polling cada 8s para sincronización en vivo
    return () => clearInterval(interval);
  }, [fetchSlots]);

  // Sembrar datos de prueba si la base está vacía
  const handleSeed = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/slots/seed`, { method: 'POST' });
      if (res.ok) {
        addActivity('Datos Sembrados', 'Canchas y slots de prueba cargados', 'info');
        fetchSlots();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const addActivity = (title: string, subtitle: string, type: 'confirmed' | 'hold' | 'info') => {
    setActivities(prev => [
      { id: Date.now().toString(), title, subtitle, time: 'Justo ahora', type },
      ...prev.slice(0, 5)
    ]);
  };

  // Abrir modal para un slot específico
  const openHoldModal = (slot: TimeSlot) => {
    setSelectedSlot(slot);
    setSpotsToHold(slot.mode === 'FULL_COURT' ? 4 : 1);
    setStatusMessage(null);
  };

  // Enviar creación de Hold
  const handleCreateHold = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSlot) return;

    setSubmitting(true);
    setStatusMessage(null);

    try {
      const payload = {
        slot_id: selectedSlot.id,
        customer_phone: customerPhone.trim(),
        customer_name: customerName.trim(),
        spots_held: selectedSlot.mode === 'FULL_COURT' ? 4 : Number(spotsToHold)
      };

      const res = await fetch(`${API_BASE}/api/v1/holds/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Error al generar el bloqueo temporal');
      }

      setStatusMessage({
        type: 'success',
        text: `Hold creado: Ref ${data.payment_reference}. Total: $${Number(data.amount_to_pay).toLocaleString('es-CO')} COP.`
      });

      setActiveHolds(prev => [data, ...prev]);
      addActivity(`Nuevo Hold: ${selectedSlot.court_name || 'Cancha'}`, `${data.customer_name} • ${data.spots_held} cupos`, 'hold');

      // Limpiar formulario y recargar
      setTimeout(() => {
        setSelectedSlot(null);
        setCustomerName('');
        setCustomerPhone('+57 ');
        fetchSlots();
      }, 1800);
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: err.message });
    } finally {
      setSubmitting(false);
    }
  };

  // Simular pago webhook (Bold / Wompi)
  const handleSimulatePayment = async (reference: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/webhooks/payment-mock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_reference: reference, status: 'APPROVED' })
      });
      if (res.ok) {
        const booking = await res.json();
        addActivity('Pago Confirmado', `Ref ${booking.payment_reference} • $${Number(booking.amount_paid).toLocaleString('es-CO')} COP`, 'confirmed');
        setActiveHolds(prev => prev.filter(h => h.payment_reference !== reference));
        fetchSlots();
      }
    } catch (err) {
      console.error('Error simulating payment:', err);
    }
  };

  // Calcular métricas
  const totalRevenue = slots.reduce((acc, s) => {
    const pricePerSpot = Number(s.price_per_spot) || 0;
    return acc + (s.booked_spots * pricePerSpot);
  }, 0);

  return (
    <div className="bg-surface text-on-surface min-h-screen font-sans">
      {/* Header Fijo */}
      <header className="fixed top-0 w-full z-50 bg-surface/80 backdrop-blur-xl pt-safe shadow-[0_1px_8px_rgba(0,0,0,0.04)] border-b border-border-subtle/50">
        <div className="h-16 flex items-center justify-between px-4 max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary font-black tracking-wider">
              YP
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-semibold text-on-surface tracking-tight">Capital Pádel Club</span>
              <div className="flex items-center gap-1.5">
                <div className={`w-1.5 h-1.5 rounded-full ${apiOnline ? 'bg-secondary animate-pulse-status' : 'bg-status-warning'}`}></div>
                <span className="text-[10px] text-secondary font-semibold uppercase tracking-wider">
                  {apiOnline ? 'API Live: 8000' : 'API Desconectada'}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {slots.length === 0 && (
              <button
                onClick={handleSeed}
                className="text-xs bg-primary/20 hover:bg-primary/30 text-primary px-3 py-1.5 rounded-full font-medium transition"
              >
                Sembrar Datos Demo
              </button>
            )}
            <button onClick={fetchSlots} title="Refrescar" className="p-2 text-on-surface-variant hover:text-primary transition-colors">
              <span className="material-symbols-outlined text-[20px]">sync</span>
            </button>
            <div className="w-8 h-8 rounded-full bg-surface-container-high border border-outline-variant flex items-center justify-center font-semibold text-xs text-primary">
              CP
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="pt-20 pb-24 px-4 max-w-7xl mx-auto">
        {/* Header Title */}
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold tracking-tight text-text-primary">Dashboard Recepción</h1>
          <span className="text-xs text-text-muted bg-surface-container-lowest px-3 py-1 rounded-full border border-border-subtle">
            Turnos & Partidos Abiertos
          </span>
        </div>

        {/* Top Toolbar: Date & Filters */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-2 bg-surface-container-lowest p-1 rounded-full border border-border-subtle shadow-sm">
            <button className="px-4 py-1.5 bg-surface-container-high rounded-full shadow-sm flex items-center gap-1.5 text-xs font-semibold text-on-surface">
              <span className="material-symbols-outlined text-primary text-[16px]">event</span>
              Hoy
            </button>
            <button className="px-4 py-1.5 rounded-full text-xs font-medium text-on-surface-variant hover:bg-surface-container-high/50 transition-colors">
              Mañana
            </button>
          </div>

          <div className="flex items-center gap-1.5 bg-surface-container-lowest p-1 rounded-full border border-border-subtle shadow-sm">
            <button
              onClick={() => setModeFilter('ALL')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
                modeFilter === 'ALL' ? 'bg-primary text-on-primary shadow-md' : 'text-on-surface-variant'
              }`}
            >
              Todos
            </button>
            <button
              onClick={() => setModeFilter('FULL_COURT')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
                modeFilter === 'FULL_COURT' ? 'bg-primary text-on-primary shadow-md' : 'text-on-surface-variant'
              }`}
            >
              Cancha Completa
            </button>
            <button
              onClick={() => setModeFilter('SPLIT_MATCH')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
                modeFilter === 'SPLIT_MATCH' ? 'bg-primary text-on-primary shadow-md' : 'text-on-surface-variant'
              }`}
            >
              Partidos Abiertos
            </button>
          </div>
        </div>

        {/* Central Section: Schedule Grid */}
        <section className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-bold text-on-surface">Grilla de Turnos</h2>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-secondary animate-pulse-status"></div>
              <span className="text-xs font-semibold text-secondary uppercase tracking-wider">En Vivo</span>
            </div>
          </div>

          {loading ? (
            <div className="h-40 flex items-center justify-center bg-surface-container-low rounded-2xl border border-border-subtle">
              <span className="text-sm text-text-muted animate-pulse">Cargando turnos desde FastAPI...</span>
            </div>
          ) : slots.length === 0 ? (
            <div className="p-8 text-center bg-surface-container-low rounded-2xl border border-dashed border-border-subtle">
              <p className="text-sm text-text-muted mb-3">No hay slots configurados para esta fecha/filtro.</p>
              <button
                onClick={handleSeed}
                className="bg-primary hover:bg-primary/90 text-on-primary text-xs font-bold px-4 py-2 rounded-full transition"
              >
                Sembrar Cancha y Turnos Demo
              </button>
            </div>
          ) : (
            <div className="w-full overflow-x-auto pb-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {slots.map((slot) => {
                  const isAvailable = slot.available_spots > 0 && slot.status !== 'BLOCKED';
                  const isOpenMatch = slot.mode === 'SPLIT_MATCH';
                  const isFullBooked = slot.status === 'FULLY_BOOKED' || slot.available_spots === 0;
                  const hasHolds = slot.held_spots > 0;

                  return (
                    <div
                      key={slot.id}
                      className={`relative rounded-xl p-4 shadow-sm transition-all duration-200 border flex flex-col justify-between min-h-[170px] ${
                        isFullBooked
                          ? 'bg-secondary-container/20 border-secondary-container/40 text-on-surface'
                          : isOpenMatch
                          ? 'bg-primary-container/15 border-primary-container/30 hover:border-primary/60'
                          : 'bg-surface-container-high border-border-subtle hover:border-primary/50'
                      }`}
                    >
                      {/* Top Tag & Time */}
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-semibold text-primary">
                            {slot.court_name || `Cancha ${slot.court_id}`}
                          </span>
                          <span className="text-[11px] font-mono bg-surface-container-lowest px-2 py-0.5 rounded text-on-surface-variant">
                            {slot.start_time.slice(0, 5)} - {slot.end_time.slice(0, 5)}
                          </span>
                        </div>

                        {/* Mode & Status Badge */}
                        <div className="flex items-center gap-1.5 mb-2">
                          {isOpenMatch ? (
                            <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider bg-primary/20 text-primary px-2 py-0.5 rounded">
                              <span className="material-symbols-outlined text-[12px]">groups</span>
                              Partido Abierto
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider bg-tertiary/20 text-tertiary px-2 py-0.5 rounded">
                              <span className="material-symbols-outlined text-[12px]">sports_tennis</span>
                              Cancha Completa
                            </span>
                          )}

                          {hasHolds && (
                            <span className="text-[10px] font-bold uppercase tracking-wider bg-tertiary-container text-on-tertiary-container px-1.5 py-0.5 rounded animate-pulse">
                              Hold ({slot.held_spots})
                            </span>
                          )}
                        </div>

                        {/* Spots indicator */}
                        <div className="mt-2">
                          <div className="flex justify-between items-center text-xs mb-1">
                            <span className="text-text-muted">Cupos:</span>
                            <span className="font-semibold text-on-surface">
                              {slot.booked_spots + slot.held_spots} / {slot.capacity}
                            </span>
                          </div>
                          {/* Progress bar */}
                          <div className="w-full bg-surface-container-lowest rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-primary h-1.5 rounded-full transition-all"
                              style={{ width: `${((slot.booked_spots + slot.held_spots) / slot.capacity) * 100}%` }}
                            ></div>
                          </div>
                        </div>
                      </div>

                      {/* Footer: Price & Action */}
                      <div className="mt-4 pt-3 border-t border-border-subtle/50 flex items-center justify-between">
                        <div className="flex flex-col">
                          <span className="text-[10px] text-text-muted uppercase">
                            {isOpenMatch ? 'Por persona' : 'Precio total'}
                          </span>
                          <span className="text-xs font-bold text-text-primary">
                            ${Number(isOpenMatch ? slot.price_per_spot : slot.total_price).toLocaleString('es-CO')} COP
                          </span>
                        </div>

                        {isAvailable ? (
                          <button
                            onClick={() => openHoldModal(slot)}
                            className="bg-primary hover:bg-primary/90 text-on-primary text-xs font-bold px-3 py-1.5 rounded-lg shadow-sm transition-all hover:scale-105 flex items-center gap-1"
                          >
                            <span className="material-symbols-outlined text-[14px]">add</span>
                            Reservar
                          </button>
                        ) : (
                          <span className="text-[11px] font-bold text-secondary flex items-center gap-1 bg-secondary/10 px-2 py-1 rounded">
                            <span className="material-symbols-outlined text-[14px]">check_circle</span>
                            Completo
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        {/* Active Holds Banner / Simulator (si existen holds pendientes) */}
        {activeHolds.length > 0 && (
          <section className="mb-8 bg-tertiary-container/15 border border-tertiary-container/40 rounded-2xl p-4 shadow-md">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-tertiary">timer</span>
                <h3 className="text-sm font-bold text-on-surface">Holds Activos (Pendientes de Pago)</h3>
              </div>
              <span className="text-xs text-text-muted">TTL: 15 min</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {activeHolds.map((h) => (
                <div key={h.payment_reference} className="bg-surface-container-high rounded-xl p-3 flex items-center justify-between border border-border-subtle">
                  <div>
                    <span className="text-xs font-mono font-bold text-primary">{h.payment_reference}</span>
                    <p className="text-xs text-on-surface">{h.customer_name} ({h.spots_held} cupo{h.spots_held > 1 ? 's' : ''})</p>
                    <p className="text-[11px] text-text-muted">${Number(h.amount_to_pay).toLocaleString('es-CO')} COP</p>
                  </div>
                  <button
                    onClick={() => handleSimulatePayment(h.payment_reference)}
                    className="bg-secondary hover:bg-secondary/90 text-on-secondary-container text-xs font-bold px-3 py-1.5 rounded-lg shadow-sm transition flex items-center gap-1"
                  >
                    <span className="material-symbols-outlined text-[14px]">payments</span>
                    Simular Pago
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Operations Panel */}
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-on-surface">Operaciones & Métricas</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* KPI Card */}
            <div className="bg-surface-container-low rounded-2xl p-5 shadow-md flex flex-col justify-between border border-border-subtle">
              <div className="flex justify-between items-start">
                <div className="flex flex-col">
                  <span className="text-xs text-text-muted uppercase tracking-wider font-semibold">Ingresos del Día</span>
                  <span className="text-3xl font-extrabold text-on-surface mt-1">
                    ${totalRevenue.toLocaleString('es-CO')} <span className="text-sm text-text-muted font-normal">COP</span>
                  </span>
                </div>
                <div className="bg-secondary/10 px-2 py-1 rounded text-secondary flex items-center gap-1 text-xs font-bold">
                  <span className="material-symbols-outlined text-[14px]">trending_up</span>
                  +18%
                </div>
              </div>

              <div className="flex items-center gap-4 mt-6">
                {/* Mini Gauge */}
                <div className="relative w-14 h-14">
                  <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                    <path className="text-surface-container-highest" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="3"></path>
                    <path className="text-primary" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeDasharray="75, 100" strokeLinecap="round" strokeWidth="3"></path>
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-[11px] font-bold text-on-surface">75%</span>
                  </div>
                </div>
                <div className="flex flex-col">
                  <span className="text-xs font-semibold text-on-surface">RevPAST (Ocupación)</span>
                  <span className="text-xs text-text-muted">Target Diario: $1.5M COP</span>
                </div>
              </div>
            </div>

            {/* Live Activity List */}
            <div className="bg-surface-container-lowest rounded-2xl p-5 shadow-sm flex flex-col gap-3 border border-border-subtle">
              <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">Actividad en Tiempo Real</h3>
              {activities.map((item) => (
                <div key={item.id} className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full ${
                    item.type === 'confirmed' ? 'bg-secondary animate-pulse-status' : item.type === 'hold' ? 'bg-tertiary' : 'bg-primary'
                  }`}></div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-on-surface truncate">{item.title}</p>
                    <p className="text-[10px] text-text-muted">{item.subtitle} • {item.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      {/* Modal para Crear Hold Temporal */}
      {selectedSlot && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-surface-container-high border border-border-subtle w-full max-w-md rounded-2xl p-6 shadow-2xl relative">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-text-primary">
                {selectedSlot.mode === 'FULL_COURT' ? 'Bloquear Cancha Completa' : 'Apartar Cupo / Partido Abierto'}
              </h3>
              <button onClick={() => setSelectedSlot(null)} className="text-text-muted hover:text-text-primary">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            <div className="bg-surface-container-lowest rounded-xl p-3 mb-4 text-xs flex justify-between items-center border border-border-subtle">
              <div>
                <p className="font-semibold text-primary">{selectedSlot.court_name || `Cancha ${selectedSlot.court_id}`}</p>
                <p className="text-text-muted">{selectedSlot.start_time.slice(0, 5)} - {selectedSlot.end_time.slice(0, 5)}</p>
              </div>
              <div className="text-right">
                <p className="text-text-muted">Disponibles</p>
                <p className="font-bold text-secondary text-sm">{selectedSlot.available_spots} cupos</p>
              </div>
            </div>

            <form onSubmit={handleCreateHold} className="flex flex-col gap-3">
              <div>
                <label className="text-xs text-text-muted block mb-1">Nombre del Cliente / Jugador</label>
                <input
                  type="text"
                  required
                  placeholder="Ej: Juan Camilo"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  className="w-full bg-surface-container-lowest border border-border-subtle rounded-xl px-3 py-2 text-sm text-on-surface focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs text-text-muted block mb-1">Teléfono (WhatsApp)</label>
                <input
                  type="text"
                  required
                  placeholder="+57 300 123 4567"
                  value={customerPhone}
                  onChange={(e) => setCustomerPhone(e.target.value)}
                  className="w-full bg-surface-container-lowest border border-border-subtle rounded-xl px-3 py-2 text-sm text-on-surface focus:outline-none focus:border-primary"
                />
              </div>

              {selectedSlot.mode === 'SPLIT_MATCH' ? (
                <div>
                  <label className="text-xs text-text-muted block mb-1">Cupos a Reservar (1 a {selectedSlot.available_spots})</label>
                  <select
                    value={spotsToHold}
                    onChange={(e) => setSpotsToHold(Number(e.target.value))}
                    className="w-full bg-surface-container-lowest border border-border-subtle rounded-xl px-3 py-2 text-sm text-on-surface focus:outline-none focus:border-primary"
                  >
                    {Array.from({ length: selectedSlot.available_spots }, (_, i) => i + 1).map((n) => (
                      <option key={n} value={n}>{n} cupo{n > 1 ? 's' : ''} (${(Number(selectedSlot.price_per_spot) * n).toLocaleString('es-CO')} COP)</option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="bg-tertiary/10 border border-tertiary/20 p-2.5 rounded-xl text-xs text-tertiary">
                  En modalidad <strong>Cancha Completa</strong> se reservan los 4 cupos simultáneamente por un total de <strong>${Number(selectedSlot.total_price).toLocaleString('es-CO')} COP</strong>.
                </div>
              )}

              {statusMessage && (
                <div className={`p-2.5 rounded-xl text-xs ${statusMessage.type === 'success' ? 'bg-secondary/20 text-secondary' : 'bg-error-container text-error'}`}>
                  {statusMessage.text}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 mt-4">
                <button
                  type="button"
                  onClick={() => setSelectedSlot(null)}
                  className="px-4 py-2 text-xs font-semibold text-text-muted hover:text-text-primary"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="bg-primary hover:bg-primary/90 text-on-primary text-xs font-bold px-5 py-2.5 rounded-xl shadow-md transition disabled:opacity-50"
                >
                  {submitting ? 'Generando Hold...' : 'Confirmar Bloqueo (TTL 15 min)'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Bottom Navigation */}
      <nav className="fixed bottom-0 w-full z-40 pb-safe bg-surface-container-high/90 backdrop-blur-xl border-t border-border-subtle">
        <div className="flex items-center justify-around h-16 max-w-md mx-auto px-4">
          <button className="flex flex-col items-center justify-center gap-1 text-primary font-bold">
            <span className="material-symbols-outlined text-[20px]">dashboard</span>
            <span className="text-[10px] uppercase tracking-wider">Dash</span>
          </button>
          <button className="flex flex-col items-center justify-center gap-1 text-on-surface-variant hover:text-primary transition">
            <span className="material-symbols-outlined text-[20px]">calendar_today</span>
            <span className="text-[10px] uppercase tracking-wider">Turnos</span>
          </button>
          <button className="flex flex-col items-center justify-center gap-1 text-on-surface-variant hover:text-primary transition">
            <span className="material-symbols-outlined text-[20px]">book_online</span>
            <span className="text-[10px] uppercase tracking-wider">Reservas</span>
          </button>
          <button className="flex flex-col items-center justify-center gap-1 text-on-surface-variant hover:text-primary transition">
            <span className="material-symbols-outlined text-[20px]">tune</span>
            <span className="text-[10px] uppercase tracking-wider">Ajustes</span>
          </button>
        </div>
      </nav>
    </div>
  );
}