import React, { createContext, useContext, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, CircleHelp, History as HistoryIcon, Home as HomeIcon, Layers, Mail, MessageCircle, MoonStar, RefreshCw, Sparkles, UserRound } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { getCategories, getQuestions, getSpreads, createReading, drawReading, revealReading, getReading, getHistory, interpretReading, register, login, logout, getCurrentUser, deleteReading, recordPageView, getAnalytics } from './api'
import { guestReadingIds, rememberGuestReading, forgetGuestReading } from './guestHistory'
import './style.css'

const BACK = `${import.meta.env.BASE_URL}assets/cards/card-back.svg`
const Draft = createContext(null)
const Auth = createContext(null)
const RESULT_PATH = '/result/'
const READING_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
function InterpretationParagraphs({ text }) {
  return text.split(/\r?\n[\t ]*\r?\n+/).filter(paragraph => paragraph.trim()).map((paragraph, index) => <p key={index}>{paragraph}</p>)
}
function readingResultPath(id) {
  return id?.length === 36 && READING_UUID.test(id) ? `${RESULT_PATH}${id.toLowerCase()}` : null
}
function authPath(path, returnTo) {
  return returnTo ? `${path}?${new URLSearchParams({ returnTo })}` : path
}
const categoryDetails = {
  'daily-life': 'มองเรื่องราวรอบตัวในแต่ละวัน', finance: 'สำรวจการเงินและการวางแผน', love: 'ทบทวนความสัมพันธ์และหัวใจ', career: 'มองเส้นทางและโอกาสในการทำงาน', guidance: 'รับฟังข้อความที่อยากชวนให้คุณใส่ใจ',
}
const spreadDetails = { 3: 'มองภาพรวมอย่างรวดเร็ว ผ่านสถานการณ์ อุปสรรค และคำแนะนำ', 5: 'สำรวจรายละเอียด สาเหตุ อุปสรรค จุดแข็ง และแนวทาง', 10: 'เซลติกครอส สำรวจสถานการณ์รอบด้านผ่านไพ่สิบตำแหน่ง' }

function useRemote(loader, dependencies = [], initialData = null) {
  const [state, setState] = useState({ loading: true, data: initialData, error: false })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    setState({ loading: true, data: attempt === 0 ? initialData : null, error: false })
    Promise.resolve().then(loader).then(data => { if (active) setState({ loading: false, data, error: false }) }).catch(error => { if (active) setState({ loading: false, data: null, error }) })
    return () => { active = false }
  }, [...dependencies, attempt])
  return { ...state, retry: () => setAttempt(n => n + 1), updateData: update => setState(current => current.data ? { ...current, data: update(current.data) } : current) }
}
function RemoteState({ state, empty = 'ยังไม่มีข้อมูลในขณะนี้', children, authAware = false }) {
  if (state.loading) return <div className="empty-state" role="status">กำลังโหลดข้อมูล…</div>
  if (authAware && state.error?.response?.status === 401) return <div className="empty-state" role="alert"><h2>กรุณาเข้าสู่ระบบเพื่อดูประวัติ</h2><p>ประวัติการเปิดไพ่ต้องใช้บัญชีผู้ใช้งาน</p><Link className="button button-outline" to="/login">เข้าสู่ระบบ</Link></div>
  if (state.error) return <div className="empty-state" role="alert"><h2>โหลดข้อมูลไม่สำเร็จ</h2><p>โปรดตรวจสอบการเชื่อมต่อ แล้วลองอีกครั้ง</p><button className="button button-outline" onClick={state.retry}><RefreshCw size={16} /> ลองอีกครั้ง</button></div>
  if (!Array.isArray(state.data)) return <div className="empty-state" role="alert"><h2>รูปแบบข้อมูลไม่ถูกต้อง</h2><p>ไม่สามารถแสดงข้อมูลจากระบบได้ในขณะนี้</p><button className="button button-outline" onClick={state.retry}>ลองอีกครั้ง</button></div>
  if (!state.data.length) return <div className="empty-state"><p>{empty}</p></div>
  return children(state.data)
}
function Header() {
  const navClass = ({ isActive }) => `nav-link ${isActive ? 'active' : ''}`
  return <header className="site-header"><div className="header-inner">
    <Link className="brand" to="/"><span className="brand-mark"><MoonStar size={21} aria-hidden="true" /></span><span>ไพ่ทาโรต์<small>TAROT READING</small></span></Link>
    <nav aria-label="เมนูหลัก">
      <NavLink end to="/" className={navClass}><HomeIcon size={16} aria-hidden="true" /><span>หน้าแรก</span></NavLink>
      <NavLink to="/categories" className={navClass}><Layers size={16} aria-hidden="true" /><span>เริ่มเปิดไพ่</span></NavLink>
      <NavLink to="/history" className={navClass}><HistoryIcon size={16} aria-hidden="true" /><span>ประวัติ</span></NavLink>
      <NavLink to="/account" className={navClass}><UserRound size={16} aria-hidden="true" /><span>บัญชี</span></NavLink>
    </nav>
  </div></header>
}

function Footer() {
  return <footer className="site-footer"><div className="container">
    <div className="footer-content">
      <div className="footer-about">
        <div className="footer-brand"><span className="footer-mark"><MoonStar size={19} aria-hidden="true" /></span><div><strong>ไพ่ทาโรต์</strong><small>TAROT READING</small></div></div>
        <h2>พื้นที่สำหรับการทบทวนตัวเอง</h2>
        <p>โปรเจกต์นี้เริ่มจากความรู้สึกที่ว่าเว็บไซต์ดูดวงหลายแห่งมีข้อจำกัดในการทำนาย จึงอยากลองสร้างพื้นที่อ่านไพ่ที่ชวนสำรวจเรื่องราวได้ลึกขึ้น พัฒนาขึ้นด้วยความสนุกและความตั้งใจในการเรียนรู้</p>
      </div>
      <div className="footer-details">
        <div><h2>เกี่ยวกับผลงาน</h2><p>บทบาทผู้พัฒนา</p><strong>Programmer</strong><a className="footer-project-link" href="https://github.com/BOXiandMaxi/taro_card" target="_blank" rel="noopener noreferrer">ดูโปรเจกต์บน GitHub <ArrowRight size={14} aria-hidden="true" /></a></div>
        <div><h2>ติดต่อ</h2><a className="footer-contact" href="mailto:keattisaksari@gmail.com"><Mail size={16} aria-hidden="true" /><span>keattisaksari@gmail.com</span></a><p className="footer-contact"><MessageCircle size={16} aria-hidden="true" /><span>LINE: boxigsl</span></p></div>
      </div>
    </div>
    <div className="footer-bottom"><span>พื้นที่สำหรับการทบทวนตัวเอง</span><Link to="/privacy">ข้อมูลส่วนบุคคล</Link></div>
  </div></footer>
}
function Page({ kicker, title, lead, back, children }) { return <section className="placeholder-section"><div className="container placeholder-container">{back && <Link className="back-link" to={back}><ArrowLeft size={16} aria-hidden="true" /> ย้อนกลับ</Link>}<p className="section-kicker">{kicker}</p><h1>{title}</h1>{lead && <p className="page-lead">{lead}</p>}{children}</div></section> }
const HERO_MAJOR_CARDS = ['the-fool', 'the-magician', 'the-high-priestess', 'the-empress', 'the-emperor', 'the-hierophant', 'the-lovers', 'the-chariot', 'strength', 'the-hermit', 'wheel-of-fortune', 'justice', 'the-hanged-man', 'death', 'temperance', 'the-devil', 'the-tower', 'the-star', 'the-moon', 'the-sun', 'judgement', 'the-world']
const HERO_RANKS = ['ace', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'page', 'knight', 'queen', 'king']
const HERO_CARDS = [...HERO_MAJOR_CARDS, ...['wands', 'cups', 'swords', 'pentacles'].flatMap(suit => HERO_RANKS.map(rank => `${rank}-of-${suit}`))]
const heroCardUrl = card => `${import.meta.env.BASE_URL}assets/cards/rws/${card}.webp`
function chooseHeroCards(previous = []) {
  const pool = HERO_CARDS.filter(card => !previous.includes(card))
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  return pool.slice(0, 5)
}
function Home() {
  const reduced = useReducedMotion()
  const homeRef = useRef(null)
  const [cards, setCards] = useState(chooseHeroCards)
  const [visibleCards, setVisibleCards] = useState([false, false, false, false, false])
  const cardsRef = useRef(cards)
  useEffect(() => {
    if (reduced) { setVisibleCards([true, true, true, true, true]); return }
    let timer
    let generation = 0
    let active = true
    const setVisibility = (index, visible) => setVisibleCards(current => current.map((value, i) => i === index ? visible : value))
    const scheduleCycle = () => {
      if (!active || document.hidden) return
      timer = window.setTimeout(async () => {
        const current = ++generation
        const next = chooseHeroCards(cardsRef.current)
        const loaded = await Promise.all(next.map(card => new Promise(resolve => {
          const image = new Image()
          image.onload = () => resolve(true)
          image.onerror = () => resolve(false)
          image.src = heroCardUrl(card)
        })))
        if (!active || document.hidden || current !== generation) return
        if (!loaded.every(Boolean)) { scheduleCycle(); return }
        const replaceCard = index => {
          if (!active || document.hidden || current !== generation) return
          setVisibility(index, false)
          timer = window.setTimeout(() => {
            const updated = [...cardsRef.current]
            updated[index] = next[index]
            cardsRef.current = updated
            setCards(updated)
            setVisibility(index, true)
            timer = window.setTimeout(() => index < 4 ? replaceCard(index + 1) : scheduleCycle(), 1050)
          }, 700)
        }
        replaceCard(0)
      }, 3000)
    }
    const showInitial = index => {
      if (!active || document.hidden) return
      setVisibility(index, true)
      timer = window.setTimeout(() => index < 4 ? showInitial(index + 1) : scheduleCycle(), 850)
    }
    const onVisibilityChange = () => {
      generation++
      window.clearTimeout(timer)
      setVisibleCards([true, true, true, true, true])
      if (!document.hidden) scheduleCycle()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    if (!document.hidden) timer = window.setTimeout(() => showInitial(0), 400)
    else setVisibleCards([true, true, true, true, true])
    return () => {
      active = false
      generation++
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [reduced])
  useEffect(() => {
    const home = homeRef.current
    if (reduced || !home || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('motion-in')
          observer.unobserve(entry.target)
        }
      })
    }, { threshold: 0.15 })
    home.querySelectorAll('.home-section-heading, .experience-panel, .feature-row, .home-spreads-heading, .home-spread-list, .home-faq-grid, .home-final-panel').forEach(element => observer.observe(element))
    return () => observer.disconnect()
  }, [reduced])
  return <div ref={homeRef}>
    <div className="home-announcement"><Sparkles size={14} aria-hidden="true" /> พื้นที่เล็ก ๆ สำหรับการทบทวนตัวเอง <span>✦</span> เปิดไพ่ได้โดยไม่ต้องสมัครสมาชิก</div>
    <section className="hero">
      <div className="container hero-inner">
        <p className="hero-label"><MoonStar size={15} aria-hidden="true" /> พื้นที่เล็ก ๆ สำหรับตัวคุณ</p>
        <h1>มีเรื่องไหนในใจ<br /><em>ที่อยากให้ไพ่ช่วยมอง?</em></h1>
        <p className="hero-description">เริ่มจากคำถามของคุณ เปิดไพ่ในจังหวะของตัวเอง และค้นพบมุมมองใหม่ไปด้วยกัน</p>
        <Link className="hero-start" to="/categories"><span><strong>วันนี้อยากสำรวจเรื่องอะไร?</strong><small>เลือกหัวข้อและคำถามที่ตรงใจคุณ</small></span><span className="hero-start-action">เริ่มเปิดไพ่ <ArrowRight size={18} aria-hidden="true" /></span></Link>
        <div className="hero-actions"><Link className="text-link light-link" to="/history">ดูประวัติการเปิดไพ่ <ArrowRight size={16} aria-hidden="true" /></Link></div>
        <div className="hero-deck" aria-hidden="true">
          {cards.map((card, index) => <img key={index} className={visibleCards[index] ? "hero-card-visible" : "hero-card-hidden"} src={heroCardUrl(card)} alt="" />)}
        </div>
      </div>
    </section>
    <section className="home-topics"><div className="container"><div className="home-section-heading"><p className="section-kicker">01 / FIND YOUR QUESTION</p><h2>ทุกคำถามมีพื้นที่<br /><em>ให้คุณได้สำรวจ</em></h2><p>เลือกเรื่องที่อยู่ในใจ แล้วเริ่มจากคำถามที่ใกล้ตัวคุณที่สุด</p></div><div className="home-topic-grid">{[['01','ชีวิตประจำวัน','มองเรื่องเล็ก ๆ ในแต่ละวัน'],['02','การเงิน','ทบทวนการวางแผน'],['03','ความรัก','สำรวจความสัมพันธ์'],['04','การงาน','มองเส้นทางและโอกาส'],['05','ข้อความจากไพ่','รับฟังสิ่งที่อยากให้ใส่ใจ']].map(([number, title, description]) => <div className="home-topic" key={number}><span>{number}</span><Sparkles size={20} aria-hidden="true" /><h3>{title}</h3><p>{description}</p></div>)}</div><Link className="text-link home-section-link" to="/categories">เลือกเรื่องที่อยากสำรวจ <ArrowRight size={16} aria-hidden="true" /></Link></div></section>
    <section className="home-experience"><div className="container"><div className="home-section-heading"><p className="section-kicker">02 / YOUR READING</p><h2>ไพ่หนึ่งสำรับ<br /><em>หลายมุมมองสำหรับคุณ</em></h2><p>ตั้งคำถาม เลือกรูปแบบ แล้วค่อย ๆ เปิดไพ่เพื่อมองเรื่องราวให้ชัดขึ้น</p></div><div className="experience-panel"><div className="experience-sidebar"><span className="experience-label">YOUR JOURNEY</span><strong>เริ่มจากเรื่อง<br />ที่อยู่ในใจ</strong><ol><li><span>01</span> เลือกคำถาม</li><li><span>02</span> เลือกรูปแบบไพ่</li><li><span>03</span> สับและเลือกไพ่</li><li><span>04</span> เปิดไพ่และอ่านความหมาย</li></ol><Link className="text-link" to="/categories">เริ่มต้น <ArrowRight size={16} aria-hidden="true" /></Link></div><div className="experience-canvas"><div className="experience-canvas-head"><span>การเปิดไพ่ของคุณ</span><span>ภาพประกอบ</span></div><div className="experience-cards">{['สถานการณ์','อุปสรรค','คำแนะนำ'].map((label, index) => <div key={label}><span>0{index + 1} / {label}</span><img src={BACK} alt="" /></div>)}</div><p>เลือกไพ่ แล้วค่อย ๆ เปิดดูความหมายทีละใบ</p></div></div></div></section>
    <section className="home-features"><div className="container"><div className="feature-row"><div className="feature-copy"><p className="section-kicker">03 / SHUFFLE & PICK</p><h2>ให้เวลาเล็กน้อย<br /><em>กับคำถามของคุณ</em></h2><p>สับไพ่ แล้วเลือกจากสำรับที่จัดวางเป็นวงกลม คุณเปลี่ยนใจได้จนกว่าจะยืนยันการเลือก</p><Link className="text-link" to="/categories">เริ่มเลือกไพ่ <ArrowRight size={16} aria-hidden="true" /></Link></div><div className="feature-visual feature-wheel" aria-hidden="true"><div className="feature-wheel-inner">{Array.from({ length: 12 }, (_, i) => <img key={i} src={BACK} alt="" style={{ '--angle': `${i * 30}deg` }} />)}<span>✦</span></div></div></div><div className="feature-row feature-row-reverse"><div className="feature-copy"><p className="section-kicker">04 / REVEAL & REFLECT</p><h2>เปิดไพ่ทีละใบ<br /><em>แล้วมองภาพรวม</em></h2><p>ดูชื่อ ความหมาย และตำแหน่งของไพ่แต่ละใบ เมื่อเข้าสู่ระบบ คุณสามารถขอคำอ่านประกอบและกลับมาดูประวัติได้</p><Link className="text-link" to="/history">ดูประวัติการเปิดไพ่ <ArrowRight size={16} aria-hidden="true" /></Link></div><div className="feature-visual feature-reveal"><div className="feature-reveal-card"><span>ภาพประกอบไพ่</span><img src={`${import.meta.env.BASE_URL}assets/cards/rws/the-star.webp`} alt="ไพ่ The Star" /><strong>ดวงดาว</strong><small>THE STAR</small></div><div className="feature-reveal-note"><Sparkles size={18} aria-hidden="true" /><strong>ทำความรู้จักไพ่</strong><p>ความหมายของไพ่เปลี่ยนไปตามคำถามและตำแหน่งที่เปิดได้</p></div></div></div></div></section>
    <section className="home-spreads"><div className="container"><p className="section-kicker">05 / CHOOSE YOUR SPREAD</p><div className="home-spreads-heading"><div><h2>เลือกมุมมอง<br /><em>ที่เหมาะกับคุณ</em></h2><p>แต่ละรูปแบบช่วยสำรวจคำถามเดียวกันในระดับความละเอียดที่ต่างกัน</p></div><Link className="text-link home-spreads-link" to="/categories">เริ่มเปิดไพ่ <ArrowRight size={16} aria-hidden="true" /></Link></div><div className="home-spread-list"><div><span>03</span><h3>ภาพรวมอย่างรวดเร็ว</h3><p>สถานการณ์ อุปสรรค และคำแนะนำ</p></div><div><span>05</span><h3>สำรวจให้ลึกขึ้น</h3><p>มองสาเหตุ จุดแข็ง และแนวทาง</p></div><div><span>10</span><h3>เซลติกครอส</h3><p>สำรวจเรื่องราวรอบด้านผ่านสิบตำแหน่ง</p></div></div></div></section>
    <section className="home-faq"><div className="container home-faq-grid"><div><p className="section-kicker">06 / GOOD TO KNOW</p><h2>ก่อนเริ่ม<br />เปิดไพ่</h2></div><div className="home-faq-list"><details><summary>ต้องเข้าสู่ระบบก่อนเปิดไพ่ไหม?</summary><p>คุณสามารถเปิดไพ่และอ่านความหมายได้โดยไม่ต้องเข้าสู่ระบบ หากต้องการคำทำนายแบบละเอียดให้เข้าสู่ระบบก่อน โดยไพ่ที่เปิดไว้ยังอยู่</p></details><details><summary>ควรเลือกไพ่กี่ใบ?</summary><p>ไพ่ 3 ใบเหมาะกับภาพรวม ส่วน 5 และ 10 ใบช่วยสำรวจรายละเอียดและมุมมองเพิ่มเติม</p></details><details><summary>ควรใช้คำอ่านอย่างไร?</summary><p>ใช้คำอ่านเป็นพื้นที่ทบทวนตนเองและพิจารณาร่วมกับข้อมูลจริง การตัดสินใจยังเป็นของคุณเสมอ</p></details></div></div></section>
    <section className="home-final"><div className="container"><div className="home-final-panel"><p className="section-kicker">A MOMENT FOR YOU</p><h2>พร้อมเริ่มต้น<br /><em>ในแบบของคุณหรือยัง?</em></h2><p>เลือกคำถาม แล้วให้ไพ่เป็นเพื่อนในการสำรวจอีกมุมหนึ่ง</p><div><Link className="button home-final-button" to="/categories">เริ่มสำรวจคำถาม <ArrowRight size={18} aria-hidden="true" /></Link><Link className="text-link" to="/history">ดูประวัติการเปิดไพ่ <ArrowRight size={16} aria-hidden="true" /></Link></div></div></div></section>
  </div>
}
function Categories() { const { setDraft } = useContext(Draft); const state = useRemote(getCategories); return <Page kicker="01 / CHOOSE A TOPIC" title="วันนี้อยากสำรวจเรื่องอะไร" lead="เลือกหัวข้อที่ใกล้เคียงกับเรื่องในใจของคุณ" back="/"><RemoteState state={state}>{rows => <div className="choice-grid">{rows.map(row => <Link key={row.id} className="choice" to="/questions" onClick={() => { sessionStorage.removeItem(PENDING_KEY); setDraft({ category: row }) }}><span className="choice-symbol"><Sparkles size={21} aria-hidden="true" /></span><h2>{row.name_th}</h2><p>{categoryDetails[row.slug] || 'เลือกคำถามที่เหมาะกับคุณ'}</p><span className="choice-action">เลือกหัวข้อนี้ <ArrowRight size={16} /></span></Link>)}</div>}</RemoteState></Page> }
function Questions() { const { draft, setDraft } = useContext(Draft); const state = useRemote(() => draft.category ? getQuestions(draft.category.id) : Promise.resolve([]), [draft.category?.id]); if (!draft.category) return <Missing />; return <Page kicker="02 / YOUR QUESTION" title="เลือกคำถามที่ตรงใจ" lead={`หัวข้อ: ${draft.category.name_th}`} back="/categories"><RemoteState state={state}>{rows => <div className="question-list">{rows.map(row => <Link className="question-choice" to="/spreads" key={row.id} onClick={() => setDraft({ category: draft.category, question: row })}><span>{row.prompt_th}</span><ArrowRight size={18} aria-hidden="true" /></Link>)}</div>}</RemoteState></Page> }
function Spreads() { const { draft, setDraft } = useContext(Draft); const state = useRemote(getSpreads); return <Page kicker="03 / CHOOSE A SPREAD" title="เลือกรูปแบบการวางไพ่" lead={draft.question ? `คำถาม: ${draft.question.prompt_th}` : 'แต่ละรูปแบบชวนมองคำถามจากมุมที่ต่างกัน'} back={draft.question ? '/questions' : '/categories'}><RemoteState state={state}>{rows => <div className="choice-grid spread-grid">{rows.map(row => <article className="choice" key={row.id}><span className="spread-number">{row.card_count}</span><h2>{row.name_th}</h2><p>{spreadDetails[row.card_count]}</p><details><summary>ดูตำแหน่งไพ่</summary><ol>{row.positions?.map(position => <li key={position.id}>{position.meaning_th}</li>)}</ol></details>{draft.question ? <Link className="button button-outline choice-button" to="/shuffle" onClick={() => setDraft({...draft, spread: row})}>เลือกรูปแบบนี้ <ArrowRight size={16} /></Link> : <Link className="button button-outline choice-button" to="/categories">เริ่มเลือกคำถาม <ArrowRight size={16} /></Link>}</article>)}</div>}</RemoteState></Page> }
function Missing() { return <Page kicker="YOUR READING" title="เริ่มต้นการเปิดไพ่" lead="กรุณาเลือกหัวข้อ คำถาม และรูปแบบไพ่ก่อน"><Link className="button button-outline" to="/categories">เลือกหัวข้อ <ArrowRight size={16} /></Link></Page> }
const DRAFT_KEY = 'tarot-draft'
const PENDING_KEY = 'tarot-pending-reading'
function readSession(key, fallback) { try { return JSON.parse(sessionStorage.getItem(key)) || fallback } catch { return fallback } }
function draftSignature(draft) { return `${draft.category?.id}:${draft.question?.id}:${draft.spread?.id}` }
function pendingFor(draft) { const saved = readSession(PENDING_KEY, null); return saved?.signature === draftSignature(draft) ? saved : null }
function savePending(value) { sessionStorage.setItem(PENDING_KEY, JSON.stringify(value)) }
const DECK_SIZE = 78
const DEAL_DURATION_MS = 800
const DEAL_STAGGER_MS = 9
const WHEEL_POSITIONS = Array.from({ length: DECK_SIZE }, (_, index) => {
  const ring = index < 39 ? 0 : index < 65 ? 1 : 2
  const angle = (index - [0, 39, 65][ring]) * 360 / [39, 26, 13][ring]
  const radius = [44, 31, 18][ring]
  const x = radius * Math.sin(angle * Math.PI / 180)
  const y = -radius * Math.cos(angle * Math.PI / 180)
  return {
    left: `${50 + x}%`, top: `${50 + y}%`, '--card-angle': `${angle}deg`,
    '--deal-from-x': `${-x}cqw`, '--deal-from-y': `${-y}cqw`,
    '--deal-delay': `${index * DEAL_STAGGER_MS}ms`, '--deal-duration': `${DEAL_DURATION_MS}ms`,
  }
})

function DeckSelection() {
  const { draft } = useContext(Draft)
  if (!draft.spread || !draft.question || !draft.category) return <Missing />
  return <DeckTable key={draftSignature(draft)} draft={draft} />
}

function DeckTable({ draft }) {
  const { user } = useContext(Auth)
  const [pending, setPending] = useState(() => pendingFor(draft))
  const [phase, setPhase] = useState(() => pending?.id ? 'selecting' : 'stacked')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const requestInFlight = useRef(false)
  const mounted = useRef(false)
  const focusAfterDeal = useRef(false)
  const selectionHeading = useRef(null)
  const reduced = useReducedMotion()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const count = draft.spread.card_count
  const selected = pending?.selected || []
  const locked = !!pending?.submitted
  const selecting = phase === 'selecting'
  const dealing = phase === 'dealing'
  const preparing = phase === 'preparing'

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    if (!dealing) return
    if (reduced) {
      setPhase('selecting')
      return
    }
    // Allow the last card to reach its position before enabling the picker.
    const timer = setTimeout(() => setPhase('selecting'), DEAL_DURATION_MS + (DECK_SIZE - 1) * DEAL_STAGGER_MS + 50)
    return () => clearTimeout(timer)
  }, [dealing, reduced])

  useEffect(() => {
    if (selecting && focusAfterDeal.current) {
      selectionHeading.current?.focus({ preventScroll: true })
      focusAfterDeal.current = false
    }
  }, [selecting])

  function isCurrent(key) {
    return mounted.current && window.location.pathname === pathname && pendingFor(draft)?.key === key
  }

  async function prepare() {
    if (phase !== 'shuffling' || requestInFlight.current) return
    requestInFlight.current = true
    setPhase('preparing')
    setError('')
    let current = pendingFor(draft)
    try {
      if (!current) {
        current = { signature: draftSignature(draft), key: crypto.randomUUID(), selected: [] }
        savePending(current)
      }
      if (!current.id) {
        const reading = await createReading({ category_id: draft.category.id, question_id: draft.question.id, spread_id: draft.spread.id }, current.key)
        if (!reading?.id) throw new Error('Invalid reading')
        if (!isCurrent(current.key)) return
        current = { ...current, id: reading.id }
        savePending(current)
      }
      if (!user) rememberGuestReading(current.id)
      setPending(current)
      focusAfterDeal.current = true
      setPhase(reduced ? 'selecting' : 'dealing')
    } catch {
      if (mounted.current && window.location.pathname === pathname) {
        setError('เตรียมสำรับไม่สำเร็จ กรุณาลองอีกครั้ง')
        setPhase('shuffling')
      }
    } finally { requestInFlight.current = false }
  }

  function toggle(index) {
    if (!selecting || requestInFlight.current) return
    const current = pendingFor(draft)
    if (!current?.id || current.submitted) return
    const indices = current.selected || []
    if (!indices.includes(index) && indices.length >= count) {
      setError(`เลือกได้ไม่เกิน ${count} ใบ`)
      return
    }
    const next = { ...current, selected: indices.includes(index) ? indices.filter(x => x !== index) : [...indices, index] }
    savePending(next)
    setPending(next)
    setError('')
  }

  async function confirm() {
    if (!selecting || requestInFlight.current) return
    const current = pendingFor(draft)
    if (!current?.id) return
    const indices = current.selected || []
    if (indices.length !== count) {
      setError(`กรุณาเลือกไพ่ให้ครบ ${count} ใบ`)
      return
    }
    requestInFlight.current = true
    setSaving(true)
    setError('')
    try {
      const submitted = { ...current, submitted: true }
      savePending(submitted)
      setPending(submitted)
      await drawReading(current.id, indices)
      if (isCurrent(current.key)) navigate(`/reveal/${encodeURIComponent(current.id)}`)
    } catch {
      if (isCurrent(current.key)) setError('ยังบันทึกไพ่ไม่ได้ กรุณาลองอีกครั้งด้วยไพ่ชุดเดิม')
    } finally {
      requestInFlight.current = false
      if (mounted.current) setSaving(false)
    }
  }

  return <Page kicker="04 / SHUFFLE & PICK" title="สับไพ่และเลือกไพ่" lead={draft.question.prompt_th} back="/spreads">
    <div className="deck-selection" data-phase={phase}>
      <div className="deck-status" role="status">
        {phase === 'stacked' && 'นึกถึงคำถามของคุณ แล้วกดสับไพ่เมื่อพร้อม'}
        {phase === 'shuffling' && 'กำลังสับไพ่ กดเสร็จแล้วเมื่อพร้อมเลือก'}
        {preparing && 'กำลังเตรียมสำรับ…'}
        {dealing && 'กำลังจ่ายไพ่…'}
        {selecting && <p ref={selectionHeading} tabIndex={-1}>เลือกแล้ว <strong>{selected.length} / {count}</strong> ใบ</p>}
      </div>
      <div className="deck-stage">
        {!selecting && !dealing && <div className={`deck-stack shuffle-deck ${!reduced && phase === 'shuffling' ? 'is-shuffling' : ''}`} aria-hidden="true">
          <img src={BACK} alt="" /><img src={BACK} alt="" /><img src={BACK} alt="" />
        </div>}
        {(selecting || dealing) && <div className="wheel-wrap">
          <div className="card-wheel" role="group" aria-label="วงไพ่ 78 ใบ" aria-hidden={dealing || undefined}>
            {WHEEL_POSITIONS.map((position, index) => {
              const order = selected.indexOf(index) + 1
              return <button key={index} type="button" disabled={dealing || saving || locked}
                className={`wheel-card ${order ? 'selected' : ''}`} style={position}
                title={`ไพ่ใบที่ ${index + 1}`} aria-label={`ไพ่ใบที่ ${index + 1}${order ? ` เลือกลำดับที่ ${order}` : ''}`}
                aria-pressed={!!order} onClick={() => toggle(index)}>
                <img src={BACK} alt="" />{order > 0 && <span>{order}</span>}
              </button>
            })}
            <div className="wheel-center" aria-hidden="true">✦</div>
          </div>
        </div>}
      </div>
      {!selecting && <div className="deck-actions button-row">
        {!dealing && <button type="button" className="button button-gold" aria-disabled={preparing}
          onClick={phase === 'stacked' ? () => setPhase('shuffling') : prepare}>
          {phase === 'stacked' ? <>สับไพ่ <RefreshCw size={16} aria-hidden="true" /></> : <>
            {preparing ? 'กำลังเตรียมสำรับ…' : 'สับไพ่เสร็จแล้ว'} <ArrowRight size={16} aria-hidden="true" />
          </>}
        </button>}
        {error && <p className="error-message" role="alert">{error}</p>}
      </div>}
      {selecting && <>
        <details className="number-picker" open>
          <summary>เลือกไพ่ด้วยหมายเลข</summary>
          <p>เริ่มที่ด้านบนของวงแล้วนับตามเข็มนาฬิกา: วงนอก 1–39 วงกลาง 40–65 วงใน 66–78</p>
          <div className="number-grid" role="group" aria-label="เลือกไพ่ด้วยหมายเลข">
            {WHEEL_POSITIONS.map((_, index) => <button key={index} type="button" disabled={saving || locked}
              className={selected.includes(index) ? 'selected' : ''} aria-label={`ไพ่ใบที่ ${index + 1}`}
              aria-pressed={selected.includes(index)} onClick={() => toggle(index)}>{index + 1}</button>)}
          </div>
        </details>
        <div className="pick-actions">
          <p className="pick-actions-count" aria-hidden="true"><strong>{selected.length} / {count}</strong></p>
          <p className="small-note">{locked ? 'หากการเชื่อมต่อขัดข้อง ให้กดยืนยันอีกครั้งด้วยไพ่ชุดเดิม' : selected.length ? `ลำดับที่เลือก: ${selected.map(i => i + 1).join(', ')}` : 'แตะไพ่ในวง หรือเลือกจากปุ่มหมายเลข'}</p>
          {error && <p className="error-message" role="alert">{error}</p>}
          <button type="button" className="button button-gold next-action" disabled={saving} onClick={confirm}>
            {saving ? 'กำลังบันทึก…' : 'ยืนยันการเลือก'} <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
      </>}
    </div>
  </Page>
}
// The reading renderer accepts only persisted cards in the documented frontend integration shape.
function ReadingPage({ result = false }) {
  const { id } = useParams()
  const { user, setIdentity } = useContext(Auth)
  const location = useLocation()
  const reduced = useReducedMotion()
  const initialReading = result && location.state?.reading?.id === id && location.state?.identity === (user?.id ?? null) ? location.state.reading : null
  const fromReveal = useRef(Boolean(initialReading))
  const interpretationRef = useRef(null)
  const scrolledToInterpretation = useRef(false)
  const state = useRemote(() => getReading(id), [id], initialReading)
  const [revealing, setRevealing] = useState(null)
  const [revealError, setRevealError] = useState(false)
  const [busy, setBusy] = useState(false)
  const [interpretError, setInterpretError] = useState(false)
  const autoRequested = useRef(null)
  const requestInFlight = useRef(false)
  const reading = state.data
  const interpretation = user ? reading?.interpretation : null
  const returnTo = readingResultPath(id)
  useEffect(() => {
    if (result && initialReading) fromReveal.current = true
    if (!result) { fromReveal.current = false; scrolledToInterpretation.current = false }
  }, [result, initialReading])
  const expected = reading?.spread?.card_count
  const validCards = [3, 5, 10].includes(expected)
    && Array.isArray(reading?.cards)
    && reading.cards.length === expected
    && reading.cards.every(item => Number.isInteger(item.position_number) && item.position_number >= 1 && item.position_number <= expected && item.position?.meaning_th && (!item.revealed || (item.card?.id && item.card?.name_th && item.card?.name_en)))
    && new Set(reading.cards.map(item => item.position_number)).size === expected
    && new Set(reading.cards.filter(item => item.revealed).map(item => item.card.id)).size === reading.cards.filter(item => item.revealed).length
  const cards = validCards ? [...reading.cards].sort((a, b) => a.position_number - b.position_number) : []
  const waitingForInterpretation = result && user && !state.error && !interpretation && (state.loading || busy || (validCards && cards.every(item => item.revealed) && !interpretError))
  async function reveal(position) {
    if (revealing !== null) return
    setRevealing(position)
    setRevealError(false)
    try {
      const revealed = await revealReading(id, position)
      if (!revealed?.revealed || revealed.position_number !== position || !revealed.card?.id || !revealed.card?.name_th || !revealed.card?.name_en || !revealed.position?.meaning_th) throw new Error('Invalid revealed card')
      state.updateData(current => ({ ...current, cards: current.cards.map(card => card.position_number === position ? revealed : card) }))
    } catch { setRevealError(true) } finally { setRevealing(null) }
  }
  async function interpret() {
    if (!user || requestInFlight.current) return
    requestInFlight.current = true
    setBusy(true)
    setInterpretError(false)
    try {
      const account = await getCurrentUser()
      if (account.id !== user.id) {
        setIdentity(account)
        state.retry()
        return
      }
      await interpretReading(id)
      forgetGuestReading(id)
      const updated = await getReading(id)
      state.updateData(() => updated)
    } catch (error) {
      if (error.response?.status === 401) {
        setIdentity(null)
        return
      }
      try {
        const current = await getReading(id)
        if (current.interpretation) { state.updateData(() => current); return }
        if (current.status === 'INTERPRETING') {
          for (let attempt = 0; attempt < 45; attempt += 1) {
            await new Promise(resolve => setTimeout(resolve, 2000))
            const updated = await getReading(id)
            if (updated.interpretation) { state.updateData(() => updated); return }
            if (updated.status !== 'INTERPRETING') break
          }
        }
      } catch (pollError) {
        if (pollError.response?.status === 401) {
          setIdentity(null)
          return
        }
      }
      setInterpretError(true)
    } finally {
      requestInFlight.current = false
      setBusy(false)
    }
  }
  useEffect(() => {
    if (user && result && !state.loading && !state.error && validCards && cards.every(item => item.revealed) && !interpretation && autoRequested.current !== id) {
      autoRequested.current = id
      void interpret()
    }
  }, [user, result, id, state.loading, state.error, validCards, interpretation, reading?.cards])
  useEffect(() => {
    if (!fromReveal.current || scrolledToInterpretation.current || state.loading || state.error || !validCards || !cards.every(item => item.revealed)) return
    if (user && !interpretation && !interpretError) return
    const target = interpretationRef.current
    if (!target) return
    scrolledToInterpretation.current = true
    target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
    target.focus({ preventScroll: true })
  }, [state.loading, state.error, validCards, interpretation, interpretError, user, reduced])
  return <Page kicker={result ? '08 / YOUR READING' : '07 / REVEAL'} title={result ? 'คำทำนายของคุณ' : 'เปิดไพ่ของคุณ'} lead={result ? 'ทบทวนความหมายในแต่ละตำแหน่งและคำแนะนำ' : 'เลือกไพ่แต่ละใบเพื่อเปิดดูผลที่บันทึกไว้'} back="/categories">
    {waitingForInterpretation && createPortal(<div className="reading-wait" role="status" aria-live="polite"><span className="reading-wait-icon" aria-hidden="true"><Sparkles size={19} /></span><div><strong>{state.loading ? 'กำลังเตรียมผลการเปิดไพ่' : 'กำลังเรียบเรียงคำทำนาย'}</strong><p>โปรดรอสักครู่ คุณสามารถดูไพ่ที่เปิดไว้ระหว่างรอได้</p></div></div>, document.body)}
    {state.loading && !state.data ? <div className="empty-state" role="status">กำลังโหลดผลการเปิดไพ่…</div> : state.error ? <div className="empty-state" role="alert"><h2>ยังโหลดผลการเปิดไพ่ไม่ได้</h2><p>โปรดตรวจสอบการเชื่อมต่อและสิทธิ์เข้าถึง แล้วลองอีกครั้ง</p><button className="button button-outline" onClick={state.retry}>ลองอีกครั้ง <RefreshCw size={16} /></button></div> : !validCards ? <div className="empty-state" role="alert"><CircleHelp className="empty-inline-icon" size={26} aria-hidden="true" /><h2>ยังแสดงผลไพ่ไม่ได้</h2><p>ข้อมูลที่ระบบส่งมายังไม่มีรายละเอียดไพ่และตำแหน่งในรูปแบบที่รองรับ</p><button className="button button-outline" onClick={state.retry}>ลองอีกครั้ง <RefreshCw size={16} /></button></div> : <>
      <div className="reading-summary"><p><strong>คำถาม:</strong> {reading.question?.prompt_th || reading.question_text || 'ไม่มีข้อมูลคำถาม'}</p><p><strong>รูปแบบ:</strong> {reading.spread?.name_th || 'ไม่มีข้อมูลรูปแบบไพ่'}</p>{result && cards.every(item => item.revealed) && <a className="account-link" href="#interpretation">ข้ามไปอ่านคำทำนาย <ArrowRight size={16} aria-hidden="true" /></a>}</div>
      {!result && <div className="reveal-progress" aria-live="polite"><span>เปิดไพ่แล้ว</span><strong>{cards.filter(item => item.revealed).length} <span>/ {cards.length} ใบ</span></strong></div>}
      <div className="revealed-grid">{cards.map(item => {
        const isOpen = item.revealed
        const meaning = Array.isArray(interpretation?.card_interpretations) ? interpretation.card_interpretations.find(entry => entry.position === item.position_number && entry.card_id === item.card?.id) : null
        return <article className={`revealed-item ${isOpen ? 'is-revealed' : ''}`} key={item.position_number}>
          <h2><span>ตำแหน่งที่ {item.position_number}</span>{item.position.meaning_th}</h2>
          <div className="revealed-content">
            <button type="button" className={`flip-card ${isOpen ? 'is-open' : ''} ${revealing === item.position_number ? 'is-revealing' : ''}`} aria-label={isOpen ? `${item.card.name_th} ${item.card.name_en}` : `เปิดไพ่ตำแหน่ง ${item.position_number} ${item.position.meaning_th}`} aria-pressed={isOpen} aria-disabled={!!revealing || isOpen} aria-busy={revealing === item.position_number} onClick={() => { if (!revealing && !isOpen) reveal(item.position_number) }}><span className="flip-inner"><span className="flip-back"><img src={BACK} alt="" /></span><span className="flip-front">{isOpen && <img className={item.orientation === 'reversed' && item.card.image_path && !item.card.image_path.includes('card-placeholder.svg') ? 'card-image-reversed' : undefined} src={item.card.image_path || `${import.meta.env.BASE_URL}assets/cards/card-placeholder.svg`} onError={event => { event.currentTarget.onerror = null; event.currentTarget.classList.remove('card-image-reversed'); event.currentTarget.src = `${import.meta.env.BASE_URL}assets/cards/card-placeholder.svg` }} alt="" />}</span></span></button>
            <div className="revealed-info">{isOpen ? <><h3>{item.card.name_th}</h3><p className="card-name-en">{item.card.name_en}</p>{item.orientation && <p className="card-orientation">{item.orientation === 'reversed' ? 'ไพ่กลับหัว' : item.orientation === 'upright' ? 'ไพ่ตั้งตรง' : ''}</p>}{item.meaning && <details><summary>ความหมายไพ่{item.orientation === 'reversed' ? 'กลับหัว' : 'ตั้งตรง'}</summary>{Array.isArray(item.meaning.keywords) && item.meaning.keywords.length > 0 && <p><strong>คำสำคัญ:</strong> {item.meaning.keywords.join(' · ')}</p>}{item.meaning.description && <p>{item.meaning.description}</p>}</details>}{result && meaning?.interpretation && <details><summary>ความหมายของไพ่ใบนี้</summary><p>{meaning.interpretation}</p></details>}</> : <div className="reveal-prompt"><span aria-hidden="true">✦</span><p className="reveal-hint" role={revealing === item.position_number ? 'status' : undefined}>{revealing === item.position_number ? 'กำลังเปิดไพ่…' : 'แตะไพ่เพื่อเปิดดู'}</p><small>ค่อย ๆ เปิดดูทีละใบ</small></div>}</div>
          </div>
        </article>
      })}</div>
      {revealError && <p className="error-message" role="alert">เปิดไพ่ไม่สำเร็จ กรุณาลองอีกครั้ง</p>}
      {result && cards.every(item => item.revealed) ? <div id="interpretation" ref={interpretationRef} tabIndex={-1} className="interpretation">
        {!user ? <>
          <p>เข้าสู่ระบบหรือสมัครสมาชิกเพื่ออ่านคำทำนายจากไพ่ชุดนี้</p>
          {returnTo && <div className="account-actions">
            <Link className="button button-gold" to={authPath('/login', returnTo)}>เข้าสู่ระบบ</Link>
            <Link className="button button-outline" to={authPath('/register', returnTo)}>สมัครสมาชิก</Link>
          </div>}
        </> : <>{interpretation && reading.interpretation_source === "database" && <p className="small-note">คำอ่านเบื้องต้นจากความหมายไพ่ในระบบ อาจยังตอบคำถามเฉพาะเจาะจงได้ไม่ครบถ้วน</p>}{interpretation?.overall_summary && <details open><summary>{reading.interpretation_source === 'database' ? 'คำตอบเบื้องต้น' : 'ภาพรวมคำทำนาย'}</summary><InterpretationParagraphs text={interpretation.overall_summary} /></details>}{interpretation?.practical_guidance?.length && <details open><summary>คำแนะนำที่นำไปใช้ได้</summary><ul>{interpretation.practical_guidance.map((guidance, index) => <li key={index}>{guidance}</li>)}</ul></details>}{interpretation?.card_connections && <details open><summary>{reading.interpretation_source === 'database' ? 'แนวทางอ่านไพ่ชุดนี้ประกอบกัน' : 'บทสรุปจากไพ่ทั้งหมด'}</summary><InterpretationParagraphs text={interpretation.card_connections} /></details>}{!interpretation && !waitingForInterpretation && <><p>ยังไม่มีคำทำนายสำหรับการเปิดไพ่ครั้งนี้</p><button className="button button-outline" onClick={interpret}>ลองขอคำทำนายอีกครั้ง</button>{interpretError && <p className="error-message" role="alert">ยังไม่สามารถขอคำทำนายได้ กรุณาลองอีกครั้ง</p>}</>}</>}
      </div> : result ? <Link className="button button-gold next-action" to={`/reveal/${encodeURIComponent(id)}`}>เปิดไพ่ที่เหลือ <ArrowRight size={16} /></Link> : cards.every(item => item.revealed) ? <Link className="button button-gold next-action" to={`/result/${encodeURIComponent(id)}`} state={{ reading, identity: user?.id ?? null }}>ดูคำทำนาย <ArrowRight size={16} /></Link> : null}
    </>}
  </Page>
}
function AuthForm({ mode }) {
  const { user, setIdentity } = useContext(Auth)
  const { search } = useLocation()
  const requestedReturn = new URLSearchParams(search).get('returnTo')
  const returnTo = requestedReturn?.startsWith(RESULT_PATH) ? readingResultPath(requestedReturn.slice(RESULT_PATH.length)) : null
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const registering = mode === 'register'
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const account = await (registering ? register(email, password) : login(email, password))
      setIdentity(account); setPassword(''); navigate(returnTo || '/account', { replace: Boolean(returnTo) })
    } catch (err) {
      const status = err.response?.status
      setError(status === 429 ? 'มีความพยายามมากเกินไป กรุณารอสักครู่แล้วลองใหม่' : status === 401 ? 'อีเมลหรือรหัสผ่านไม่ถูกต้อง' : status === 409 ? 'อีเมลนี้มีบัญชีอยู่แล้ว' : status === 422 ? 'กรุณาตรวจสอบอีเมลและรหัสผ่าน' : 'ไม่สามารถดำเนินการได้ กรุณาลองอีกครั้ง')
    } finally { setBusy(false) }
  }
  if (user && returnTo) return <Navigate to={returnTo} replace />
  if (user) return <Page kicker="ACCOUNT" title="คุณเข้าสู่ระบบแล้ว" back="/"><Link className="button button-outline" to="/account">ดูบัญชีของฉัน</Link></Page>
  return <Page kicker="ACCOUNT" title={registering ? 'สมัครสมาชิก' : 'เข้าสู่ระบบ'} lead="เข้าสู่ระบบเพื่อเก็บและดูประวัติการเปิดไพ่" back="/">
    <form className="account-form" onSubmit={submit}>
      <label htmlFor="account-email">อีเมล</label><input id="account-email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={event => setEmail(event.target.value)} />
      <label htmlFor="account-password">รหัสผ่าน</label><input id="account-password" type="password" autoComplete={registering ? 'new-password' : 'current-password'} required minLength={registering ? 8 : 1} maxLength={128} value={password} onChange={event => setPassword(event.target.value)} aria-describedby={registering ? "password-hint" : undefined} />{registering && <small id="password-hint">รหัสผ่านอย่างน้อย 8 ตัวอักษร</small>}
      {error && <p className="error-message" role="alert">{error}</p>}
      <button className="button button-gold" disabled={busy}>{busy ? 'กำลังดำเนินการ…' : registering ? 'สมัครสมาชิก' : 'เข้าสู่ระบบ'}</button>
      <p>{registering ? 'มีบัญชีแล้ว?' : 'ยังไม่มีบัญชี?'} <Link className="account-link" to={authPath(registering ? '/login' : '/register', returnTo)}>{registering ? 'เข้าสู่ระบบ' : 'สมัครสมาชิก'}</Link></p>
    </form>
  </Page>
}
function Account() {
  const { user, setIdentity } = useContext(Auth); const [busy, setBusy] = useState(false); const [error, setError] = useState(false); const navigate = useNavigate()
  async function signOut() { setBusy(true); setError(false); try { await logout(); setIdentity(null); navigate('/') } catch { setError(true) } finally { setBusy(false) } }
  return <Page kicker="ACCOUNT" title="บัญชีของฉัน" back="/">{user ? <div className="account-panel"><p>เข้าสู่ระบบด้วย <strong>{user.email}</strong></p><div className="account-actions"><Link className="button button-gold" to="/history">ดูประวัติการเปิดไพ่</Link>{user.role === 'admin' && <Link className="button button-outline" to="/admin/analytics">สถิติเข้าชม</Link>}<button className="button button-outline" disabled={busy} onClick={signOut}>{busy ? 'กำลังออกจากระบบ…' : 'ออกจากระบบ'}</button></div>{error && <p className="error-message" role="alert">ออกจากระบบไม่สำเร็จ กรุณาลองอีกครั้ง</p>}</div> : <div className="account-panel"><p>เข้าสู่ระบบเพื่อดูประวัติ หรือเปิดไพ่แบบไม่สมัครสมาชิกได้</p><div className="account-actions"><Link className="button button-gold" to="/login">เข้าสู่ระบบ</Link><Link className="button button-outline" to="/register">สมัครสมาชิก</Link></div></div>}</Page>
}
async function loadHistory(user) {
  const accountRows = user ? await getHistory() : []
  const accountIds = new Set(accountRows.map(row => row.id))
  const guestRows = []
  const ids = guestReadingIds().filter(id => !accountIds.has(id))
  for (let offset = 0; offset < ids.length; offset += 8) {
    const batch = await Promise.all(ids.slice(offset, offset + 8).map(async id => {
      try {
        const reading = await getReading(id)
        const fullyRevealed = reading.cards?.length === reading.spread?.card_count &&
          reading.cards?.length > 0 && reading.cards.every(item => item.revealed)
        return reading.status === 'COMPLETED' || fullyRevealed ? reading : null
      } catch (error) {
        if ([401, 404, 422].includes(error.response?.status)) { forgetGuestReading(id); return null }
        throw error
      }
    }))
    guestRows.push(...batch.filter(Boolean))
  }
  const rows = new Map([...accountRows, ...guestRows].map(row => [row.id, row]))
  return [...rows.values()].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
}
function History() {
  const { user } = useContext(Auth)
  const state = useRemote(() => loadHistory(user), [user?.id]); const [deleting, setDeleting] = useState(null); const [error, setError] = useState('')
  async function remove(id) {
    if (!window.confirm('ลบประวัติการเปิดไพ่ครั้งนี้ใช่ไหม? การลบไม่สามารถย้อนกลับได้')) return
    setDeleting(id); setError('')
    try { await deleteReading(id); forgetGuestReading(id); state.retry() } catch { setError('ลบประวัติไม่สำเร็จ กรุณาลองอีกครั้ง') } finally { setDeleting(null) }
  }
  return <Page kicker="YOUR JOURNEY" title="ประวัติการเปิดไพ่" lead="กลับมาทบทวนคำถามและเรื่องราวที่ผ่านมา" back="/">{error && <p className="error-message" role="alert">{error}</p>}<RemoteState state={state} authAware empty={user ? "ยังไม่มีประวัติการเปิดไพ่" : "ยังไม่มีประวัติในเบราว์เซอร์นี้ หลังเปิดไพ่เสร็จจะดูย้อนหลังได้ที่นี่"}>{rows => <div className="history-list">{rows.map(row => <article className="history-item" key={row.id}><div className="history-meta"><span>{row.category?.name_th || 'การเปิดไพ่'}</span>{row.created_at && <time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'short' })}</time>}</div><h2>{row.question?.prompt_th || row.question_text || 'การเปิดไพ่'}</h2><p>{row.cards?.filter(item => item.card).map(item => item.card.name_th).join(' · ') || 'ยังไม่มีไพ่ที่เปิด'}</p>{row.interpretation_summary && <p>{row.interpretation_summary}</p>}<div className="history-actions"><Link className="account-link" to={`/result/${encodeURIComponent(row.id)}`}>ดูรายละเอียด <ArrowRight size={16} aria-hidden="true" /></Link><button type="button" className="history-delete" disabled={deleting !== null} onClick={() => remove(row.id)}>{deleting === row.id ? 'กำลังลบ…' : 'ลบประวัติ'}</button></div></article>)}</div>}</RemoteState></Page>
}
const ANALYTICS_PAGES = {
  '/': ['home', 'หน้าแรก'], '/categories': ['categories', 'เลือกหัวข้อ'],
  '/questions': ['questions', 'เลือกคำถาม'], '/spreads': ['spreads', 'เลือกรูปแบบไพ่'],
  '/shuffle': ['shuffle', 'สับและเลือกไพ่'], '/history': ['history', 'ประวัติ'],
  '/account': ['account', 'บัญชี'], '/login': ['login', 'เข้าสู่ระบบ'],
  '/register': ['register', 'สมัครสมาชิก'], '/privacy': ['privacy', 'ข้อมูลส่วนบุคคล'],
}
const PAGE_NAMES = Object.fromEntries([...Object.values(ANALYTICS_PAGES), ['reveal', 'เปิดไพ่'], ['result', 'ผลคำทำนาย']])
function analyticsRoute(pathname) {
  if (ANALYTICS_PAGES[pathname]) return ANALYTICS_PAGES[pathname][0]
  const match = pathname.match(/^\/(reveal|result)\/([^/]+)$/)
  return match && READING_UUID.test(match[2]) ? match[1] : null
}

function Analytics() {
  const { user } = useContext(Auth)
  const [days, setDays] = useState(7)
  const state = useRemote(() => user?.role === 'admin' ? getAnalytics(days) : Promise.resolve(null), [user?.id, user?.role, days])
  const data = state.data
  return <Page kicker="ADMIN" title="สถิติเข้าชม" lead="ดูภาพรวมการเปิดหน้าเว็บตามเวลาไทย" back="/account">
    {!user ? <div className="empty-state"><p>กรุณาเข้าสู่ระบบด้วยบัญชีผู้ดูแล</p><Link className="button button-outline" to="/login">เข้าสู่ระบบ</Link></div>
      : user.role !== 'admin' ? <div className="empty-state" role="alert"><p>บัญชีนี้ไม่มีสิทธิ์ดูสถิติ</p></div>
      : <>
        <div className="analytics-period" role="group" aria-label="ช่วงเวลาที่แสดง">
          {[[1, 'วันนี้'], [7, '7 วัน'], [30, '30 วัน']].map(([value, label]) => <button key={value} type="button" aria-pressed={days === value} onClick={() => setDays(value)}>{label}</button>)}
        </div>
        {state.loading ? <div className="empty-state" role="status">กำลังโหลดสถิติ…</div>
          : state.error ? <div className="empty-state" role="alert"><p>{state.error.response?.status === 403 ? 'บัญชีนี้ไม่มีสิทธิ์ดูสถิติ' : state.error.response?.status === 401 ? 'เซสชันหมดอายุ กรุณาเข้าสู่ระบบอีกครั้ง' : 'โหลดสถิติไม่สำเร็จ กรุณาลองอีกครั้ง'}</p>{![401, 403].includes(state.error.response?.status) && <button className="button button-outline" onClick={state.retry}>ลองอีกครั้ง</button>}</div>
          : data && <div className="analytics-report">
            <div className="analytics-totals" aria-label="ภาพรวมสถิติ">
              <div><span>ยอดเปิดหน้า</span><strong>{data.page_views.toLocaleString('th-TH')}</strong><small>ครั้ง</small></div>
              <div><span>เบราว์เซอร์รายวันโดยประมาณ</span><strong>{data.browser_days.toLocaleString('th-TH')}</strong><small>{days === 1 ? 'เบราว์เซอร์' : 'รวมรายวัน'}</small></div>
            </div>
            <p className="analytics-note">เบราว์เซอร์เดียวกันที่เข้ามาหลายวันจะถูกนับในแต่ละวัน และการล้างคุกกี้หรือใช้อุปกรณ์อื่นอาจทำให้ถูกนับเพิ่ม</p>
            <p className="analytics-breakdown">ยอดเปิดหน้า: เข้าสู่ระบบ {data.signed_in_views.toLocaleString('th-TH')} ครั้ง · ผู้เยี่ยมชม {data.guest_views.toLocaleString('th-TH')} ครั้ง</p>
            <section className="analytics-section"><h2>สถิติรายวัน</h2>
              {data.daily.length ? <div className="analytics-table-wrap"><table><thead><tr><th scope="col">วันที่</th><th scope="col">เปิดหน้า</th><th scope="col">เบราว์เซอร์โดยประมาณ</th></tr></thead><tbody>{data.daily.map(row => <tr key={row.day}><th scope="row">{row.day}</th><td>{row.page_views.toLocaleString('th-TH')}</td><td>{row.browser_days.toLocaleString('th-TH')}</td></tr>)}</tbody></table></div> : <p>ยังไม่มีข้อมูลในช่วงเวลานี้</p>}
            </section>
            <section className="analytics-section"><h2>หน้าที่เปิดบ่อย</h2>{data.top_pages.length ? <ol className="analytics-pages">{data.top_pages.map(row => <li key={row.route_key}><span>{PAGE_NAMES[row.route_key] || 'หน้าอื่น'}</span><strong>{row.page_views.toLocaleString('th-TH')} ครั้ง</strong></li>)}</ol> : <p>ยังไม่มีข้อมูลในช่วงเวลานี้</p>}</section>
          </div>}
      </>}
  </Page>
}

function Privacy() { return <Page kicker="PRIVACY" title="ข้อมูลส่วนบุคคล" back="/"><div className="account-panel"><p>คำถามและคำทำนายของคุณอาจถูกส่งไปประมวลผลกับผู้ให้บริการ AI ภายนอกเมื่อเปิดใช้งานบริการดังกล่าว</p><p>ประวัติของผู้เยี่ยมชมดูได้ในเบราว์เซอร์ที่เปิดไพ่ขณะที่สิทธิ์เข้าถึงยังใช้ได้ และสามารถลบรายการได้จากหน้าประวัติ</p><p>เมื่อเข้าสู่ระบบ คำอ่านที่เปิดขณะใช้บัญชีจะอยู่ในประวัติของบัญชีนั้น</p><p>เว็บไซต์ใช้คุกกี้ระยะสั้นเพื่อรวบรวมสถิติการเปิดหน้าและจำนวนเบราว์เซอร์โดยประมาณ ข้อมูลสถิติไม่เก็บอีเมล IP คำถาม หรือรหัสการอ่าน และเก็บไว้ประมาณ 30 วัน คุณสามารถล้างหรือปิดกั้นคุกกี้ในเบราว์เซอร์ได้</p></div></Page> }
function App() {
  const [draft, setDraft] = useState(() => readSession(DRAFT_KEY, {})); const [auth, setAuth] = useState({ loading: true, user: null, error: false }); const [authAttempt, setAuthAttempt] = useState(0)
  const location = useLocation(); const reduced = useReducedMotion()
  const readingTransition = location.pathname.match(/^\/(?:reveal|result)\/([^/]+)$/)
  const lastTrackedNavigation = useRef(null)
  function setIdentity(user) {
    const identity = user ? String(user.id) : 'guest'
    const previous = sessionStorage.getItem('tarot-identity')
    if (previous !== identity) { if (previous === 'guest') { const pending = readSession(PENDING_KEY, null); if (pending?.id) rememberGuestReading(pending.id) } sessionStorage.removeItem(PENDING_KEY); sessionStorage.removeItem(DRAFT_KEY); setDraft({}) }
    sessionStorage.setItem('tarot-identity', identity); setAuth({ loading: false, user, error: false })
  }
  useEffect(() => { let active = true; getCurrentUser().then(user => { if (active) setIdentity(user) }).catch(error => { if (!active) return; if (error.response?.status === 401) setIdentity(null); else setAuth({ loading: false, user: null, error: true }) }); return () => { active = false } }, [authAttempt])
  useEffect(() => { if (!auth.loading && !auth.error) sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft)) }, [draft, auth.loading, auth.error])
  useEffect(() => {
    const route = analyticsRoute(location.pathname)
    const navigation = `${location.key}:${location.pathname}`
    if (auth.loading || auth.error || lastTrackedNavigation.current === navigation) return
    lastTrackedNavigation.current = navigation
    if (route && typeof globalThis.crypto?.randomUUID === 'function') recordPageView(globalThis.crypto.randomUUID(), route).catch(() => {})
  }, [location.key, location.pathname, auth.loading, auth.error])
  if (auth.loading || auth.error) return <main className="container"><div className="empty-state" role={auth.error ? 'alert' : 'status'}>{auth.error ? <><p>ตรวจสอบบัญชีไม่สำเร็จ กรุณาตรวจสอบการเชื่อมต่อ</p><button className="button button-outline" onClick={() => { setAuth({ loading: true, user: null, error: false }); setAuthAttempt(n => n + 1) }}>ลองอีกครั้ง</button></> : 'กำลังตรวจสอบบัญชี…'}</div></main>
  return <Auth.Provider value={{user: auth.user, setIdentity}}><Draft.Provider value={{draft, setDraft}}><a className="skip-link" href="#main">ข้ามไปยังเนื้อหา</a><Header /><main id="main" tabIndex="-1"><AnimatePresence mode="wait"><motion.div key={readingTransition ? `reading:${readingTransition[1]}` : location.pathname} initial={reduced ? false : {opacity: 0, y: 6}} animate={{opacity: 1, y: 0}} exit={reduced ? {} : {opacity: 0}} transition={{duration: .18}}><Routes location={location}><Route path="/" element={<Home />} /><Route path="/categories" element={<Categories />} /><Route path="/questions" element={<Questions />} /><Route path="/spreads" element={<Spreads />} /><Route path="/shuffle" element={<DeckSelection />} /><Route path="/pick" element={<Navigate to="/shuffle" replace />} /><Route path="/reveal/:id" element={<ReadingPage />} /><Route path="/result/:id" element={<ReadingPage result />} /><Route path="/history" element={<History />} /><Route path="/login" element={<AuthForm key="login" mode="login" />} /><Route path="/register" element={<AuthForm key="register" mode="register" />} /><Route path="/account" element={<Account />} /><Route path="/admin/analytics" element={<Analytics />} /><Route path="/privacy" element={<Privacy />} /><Route path="*" element={<Page kicker="PAGE NOT FOUND" title="ไม่พบหน้าที่คุณกำลังมองหา"><Link className="button button-outline" to="/">กลับหน้าแรก</Link></Page>} /></Routes></motion.div></AnimatePresence></main><Footer /></Draft.Provider></Auth.Provider>
}
createRoot(document.getElementById('root')).render(<React.StrictMode><BrowserRouter><App /></BrowserRouter></React.StrictMode>)
